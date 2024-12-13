# QuicerThanQuic
Implements Top-layered Improvements to optimize CPU utilization of the client while downloading video files from a server. Used aioquic <<https://github.com/aiortc/aioquic>> as base and built optimizations on top of that.

REQUIREMENTS:
Clone aioquic and install it in local machine.
Installation guide can be found @: <<https://github.com/aiortc/aioquic/blob/main/README.rst>>
Steps : 
1. Clone: <<https://github.com/aiortc/aioquic>> | git clone https://github.com/aiortc/aioquic.git
2. sudo apt install python3-pip python3-dev build-essential libssl-dev libffi-dev
3. python3 -m venv "Virtual Env Name" (Optional to get a local installation rather than system wide--might break core files)
4. source "Virtual Env Name"/bin/activate
5. cd aioquic
6. pip install -r requirements/doc.txt //NECESSARY REQUIREMENTS 
7. pip install . dnslib jinja2 starlette wsproto //NECESSARY REQUIREMENTS 
8. pip install . //INSTALLS AIOQUIC IN LOCAL ENV
9. Place server side code and client side code
10. Run Server: python3 new_server.py --host 0.0.0.0 --port 4433 --cert server_cert.pem --key server_key.pem --video ../video/sample_video.mp4
11. Run Client: python3 new_client.py --host SERVER_IP_HERE --port 4433 --cert client_cert.pem --key client_key.pem --output downloaded_video.mp4 / Or run monitor_perf.py -> captures CPU utilization and download duration over [10,50] Mbps Bandwidths.

Can make use of two separate machines 1 runnning server and another running Client.
Be sure to place server/ and client/ inside aioquic/ so that imports are handled properly.
