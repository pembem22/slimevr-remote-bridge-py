import argparse
import asyncio
import logging
import socket
from typing import Any, Dict

from aiortc import (
    RTCIceCandidate,
    RTCPeerConnection,
    RTCSessionDescription,
    RTCDataChannel,
)
from aiortc.contrib.signaling import object_from_string, object_to_string

from aioudp import open_remote_endpoint, Endpoint


async def offer(pc: RTCPeerConnection):
    await pc.setLocalDescription(await pc.createOffer())

    print("Send this into another instance:")
    print("```")
    print(object_to_string(pc.localDescription))
    print("```")
    print()
    print("Paste the response here:")

    answer = object_from_string(input())
    assert isinstance(answer, RTCSessionDescription)
    await pc.setRemoteDescription(answer)


async def answer(pc: RTCPeerConnection):
    print("Paste the offer here:")
    offer = object_from_string(input())
    assert isinstance(offer, RTCSessionDescription)
    await pc.setRemoteDescription(offer)
    print()

    answer = await pc.createAnswer()
    assert answer is not None
    await pc.setLocalDescription(answer)
    print("Send this into another instance:")
    print("```")
    print(object_to_string(pc.localDescription))
    print("```")
    print()


async def main():
    parser = argparse.ArgumentParser(description="Data channels ping/pong")
    parser.add_argument("role", choices=["offer", "answer"])
    parser.add_argument("--verbose", "-v", action="count")

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    pc = RTCPeerConnection()

    @pc.on("connectionstatechange")
    def connection_state_change():
        print(f"State: {pc.connectionState}")

    role = args.role
    if role == "offer":
        channel = pc.createDataChannel("data", ordered=False)
        await offer(pc)
    else:
        channel = None
        channel_event = asyncio.Event()

        @pc.on("datachannel")
        def on_datachannel(data_channel: RTCDataChannel):
            nonlocal channel, channel_event

            assert data_channel.label == "data"

            channel = data_channel
            channel_event.set()

        await answer(pc)
        await channel_event.wait()

    assert channel is not None

    mac_to_socket: Dict[bytes, Endpoint] = dict()

    @channel.on("message")
    async def on_message(message: str | bytes):
        nonlocal mac_to_socket

        assert isinstance(message, bytes)
        mac = message[0:6]
        data = message[6:]

        if role == "offer":
            if mac not in mac_to_socket:
                sock = await open_remote_endpoint("127.0.0.1", 6969)
                mac_to_socket[mac] = sock

                async def socket_loop():
                    assert channel is not None
                    current_mac = mac[:]
                    while True:
                        data, address = await sock.receive()
                        channel.send(current_mac + data)

                asyncio.create_task(socket_loop())

            sock = mac_to_socket[mac]
            sock.send(data)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    asyncio.ensure_future(main())
    loop.run_forever()
