import argparse
import asyncio
import logging
import ssl
from aioquic.asyncio.client import connect
from aioquic.quic.connection import QuicConnection
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import QuicEvent, StreamDataReceived
from aioquic.asyncio.protocol import QuicConnectionProtocol

class VideoClientProtocol(QuicConnectionProtocol):
    def __init__(self, quic: QuicConnection, output_file: str, finished: asyncio.Event):
        # Pass the QuicConnection as 'quic=' to the parent constructor
        super().__init__(quic=quic)
        self.output_file = output_file
        self.finished = finished
        self.file_handle = open(self.output_file,"wb")

    def quic_event_received(self, event: QuicEvent):
        if isinstance(event, StreamDataReceived):
            self.file_handle.write(event.data)
            self.file_handle.flush()
            if event.end_stream:
                self.file_handle.close()
                logging.info(f"Video saved to {self.output_file}")
                self.finished.set()

async def main(server_host, server_port, output_file, cafile=None, verify_mode=None):
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("quic.client")

    configuration = QuicConfiguration(
        is_client=True,
        alpn_protocols=["hq-29"],
    )
    
    configuration.load_cert_chain(certfile=cert, keyfile=key)

    finished = asyncio.Event()

    async with connect(
        server_host,
        server_port,
        configuration=configuration,
        create_protocol=lambda connection, stream_handler: VideoClientProtocol(
            quic=connection,
            output_file=output_file,
            finished=finished
        )
    ) as client:
        # Create a bidirectional stream and send the request
        stream_id = client._quic.get_next_available_stream_id(is_unidirectional=False)
        client._quic.send_stream_data(stream_id, b"GET_VIDEO", end_stream=True)

        # Wait until the entire file is received
        await finished.wait()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="QUIC video transfer client")
    parser.add_argument("--host", type=str, required=True, help="Server IP/hostname")
    parser.add_argument("--port", type=int, default=4433, help="Server port (default: 4433)")
    parser.add_argument("--cert", type=str, default="client_cert.pem",
                        help="Path to the server certificate file (default: client_cert.pem)")
    parser.add_argument("--key", type=str, default="client_key.pem",
                        help="Path to the server private key file (default: client_key.pem)")
    parser.add_argument("--output", type=str, default="received_video.mp4",
                        help="Output file for the received video (default: received_video.mp4)")

    args = parser.parse_args()
    verify_mode = ssl.CERT_NONE if args.no_verify else None

    asyncio.run(main(args.host, args.port, args.output, cafile=args.cafile, verify_mode=verify_mode))