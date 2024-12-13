import argparse
import asyncio
import logging
import os
import ssl

from aioquic.asyncio import serve
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import QuicEvent, StreamDataReceived
from aioquic.asyncio.protocol import QuicConnectionProtocol

class VideoTransferServerProtocol(QuicConnectionProtocol):
    def __init__(self, quic, video_path: str):
        super().__init__(quic=quic)
        self.video_path = video_path

    def quic_event_received(self, event: QuicEvent):
        if isinstance(event, StreamDataReceived):
            request = event.data.decode('utf-8').strip()
            if request == "GET_VIDEO":
                if os.path.exists(self.video_path):
                    with open(self.video_path, "rb") as f:
                        data = f.read()
                    self._quic.send_stream_data(event.stream_id, data, end_stream=True)
                    logging.info(f"Sent video file '{self.video_path}' to client.")
                else:
                    error_msg = "Video not found on server."
                    self._quic.send_stream_data(event.stream_id, error_msg.encode('utf-8'), end_stream=True)
                    logging.warning("Requested video not found.")

async def main(host, port, cert, key, video):
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("quic.server")

    configuration = QuicConfiguration(
        is_client=False,
        alpn_protocols=["hq-29"],
    )
    configuration.load_cert_chain(certfile=cert, keyfile=key)

    def protocol_factory(connection, stream_handler):
        return VideoTransferServerProtocol(quic=connection, video_path=video)

    logger.info(f"Starting QUIC server on {host}:{port} serving '{video}'")
    server = await serve(
        host,
        port,
        configuration=configuration,
        create_protocol=protocol_factory,
    )

    # Keep the server running indefinitely
    await asyncio.Event().wait()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="QUIC video transfer server")
    parser.add_argument("--host", type=str, default="0.0.0.0",
                        help="The host to bind to (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=4433,
                        help="The port to bind to (default: 4433)")
    parser.add_argument("--cert", type=str, default="ssl_cert.pem",
                        help="Path to the server certificate file (default: ssl_cert.pem)")
    parser.add_argument("--key", type=str, default="ssl_key.pem",
                        help="Path to the server private key file (default: ssl_key.pem)")
    parser.add_argument("--video", type=str, required=True,
                        help="Path to the video file to send")
    args = parser.parse_args()

    asyncio.run(main(args.host, args.port, args.cert, args.key, args.video))
