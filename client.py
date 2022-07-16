import logging
import socket
import asyncio
import websockets

from message import Message

class WsClient(object):
    def __init__(self, user_name, url, **kwargs):
        self.user_name = user_name
        self.url = url
        self.read_timeout = kwargs.get('read_timeout', 1)
        self.write_timeout = kwargs.get('write_timeout', 1)
        self.ping_timeout = kwargs.get('ping_timeout', 1)
        self.sleep_time = kwargs.get('sleep_time', 5)
        self.connected = False
        self.loop = kwargs.get('loop') or asyncio.get_event_loop()
        self.que_send = asyncio.Queue(loop=self.loop)
        self.que_recv = asyncio.Queue(loop=self.loop)

    def start(self):
        self.loop.run_until_complete(self.repl())

    async def send_handler(self, ws):
        while True:
            msg = await self.que_send.get()
            try:
                await asyncio.wait_for(ws.send(msg.json()), timeout=self.write_timeout, loop=self.loop)
            except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
                try:
                    pong = await ws.ping()
                    await asyncio.wait_for(pong, timeout=self.ping_timeout, loop=self.loop)
                    logging.debug('Ping OK, keeping connection alive...')
                    continue
                except:
                    logging.debug(
                    'Ping error - retrying connection in {} sec (Ctrl-C to quit)'.format(self.sleep_time))
                    self.connected = False
                    await asyncio.sleep(self.sleep_time, loop=self.loop)
                    break
            
    async def recv_handler(self, ws):
        while True:
            try:
                data = await asyncio.wait_for(ws.recv(), timeout=self.read_timeout, loop=self.loop)
                msg = Message.from_json(data)
                logging.debug('> {}'.format(msg))
                await self.que_recv.put(msg)
            except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
                try:
                    pong = await ws.ping()
                    await asyncio.wait_for(pong, timeout=self.ping_timeout, loop=self.loop)
                    logging.debug('Ping OK, keeping connection alive...')
                    continue
                except:
                    logging.debug(
                    'Ping error - retrying connection in {} sec (Ctrl-C to quit)'.format(self.sleep_time))
                    self.connected = False
                    await asyncio.sleep(self.sleep_time, loop=self.loop)
                    break

    async def repl(self):
        while True:
            try:
                async with websockets.connect(self.url) as ws:
                    self.connected = True
                    send_task = asyncio.ensure_future(self.send_handler(ws), loop=self.loop)
                    recv_task = asyncio.ensure_future(self.recv_handler(ws), loop=self.loop)

                    done, pending = await asyncio.wait([send_task, recv_task],
                            loop=self.loop, return_when=asyncio.FIRST_COMPLETED)
                    for task in pending:
                        task.cancel()
            
            except socket.gaierror as err:
                logger.debug(
                        'Socket error - retrying connection in {} sec (Ctrl-C to quit)'.format(self.sleep_time))
                await asyncio.sleep(self.sleep_time, loop=self.loop)
                continue
            except Exception as err:
                logging.error(err)
                break

if __name__ == '__main__':
    import aioconsole
    user_name = "bob"
    url = "ws://localhost:5555"
    client = WsClient(user_name, url) 
#    client.start()

    async def interact(client):
        reader, writer = await aioconsole.get_standard_streams()
        while True:
            text = await reader.readline()
            text = text.decode()
            if not text:
                continue
            msg = Message(
                sender=user_name,
                text=text
            )
            print(f"<< {msg}")
            await client.que_send.put(msg)
            if not client.connected:
                break

    async def output(client):
        while True:
            try:
                msg = await asyncio.wait_for(client.que_recv.get(), timeout=1)
                print(f">> {msg}")
            except asyncio.TimeoutError:
                if not client.connected:
                    break
            except Exception as err:
                logging.exception(err)
                logging.error('connection failed')
                break
    
    task = asyncio.wait([client.repl(), interact(client), output(client)])
    asyncio.get_event_loop().run_until_complete(task)
    

