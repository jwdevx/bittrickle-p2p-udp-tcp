#!/usr/bin/env python3
# -*- coding:utf-8 -*-

'''
Filename: client.py
Usage: python3 client.py <server_port>

COMP3331/9331 Computer Networks and Applications Assignment T3 2024 - BitTrickle
Computer Networks and Applications - BitTrickle
The client is a command-shell interpreter that allows a user to join the
peer-to-peer network and interact with it in various ways, such as making files
available to the network, and retrieving files from the network.

Example functionality, between central indexing server, and two authenticated,
active peers in the network, “A” and “B”

    1. “A” informs the server that they wish to make “X.mp3” available to the network.
    2. The server responds to “A” indicating that the file has been successfully indexed.
    3. “B” queries the server where they might find “X.mp3”.
    4. The server responds to “B” indicating that “A” has a copy of “X.mp3”.
    5. “B” establishes a TCP connection with “A” and requests “X.mp3”.
    6. “A” reads “X.mp3” from disk and sends it over the established TCP connection, which “B”
        receives and writes to disk.
'''

import socket
import threading
import time
import sys
from concurrent.futures import ThreadPoolExecutor
import argparse
import os
from typing import Tuple, Optional

BUFFER_SIZE: int = 1024

def main() -> None:
    '''
    Main function to initialize the client.
    Parses server port input, creates socket connections, and starts the UDP client.
    '''
    if len(sys.argv) != 2:
        sys.exit("Usage: python3 client.py <server_port>")

    parser = argparse.ArgumentParser()
    parser.add_argument('server_port', type=int, help='UDP port of the server')
    args = parser.parse_args()
    udp_server_address = ('127.0.0.1', args.server_port)

    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_socket.bind(('127.0.0.1', 0))
    tcp_listening_port = tcp_socket.getsockname()[1]
    stop_event = threading.Event()

    # Start UDP client and start authentication process
    udp_client = UDP_Client(udp_server_address, udp_socket,
                            tcp_socket, tcp_listening_port, stop_event)
    try:
        udp_client.start()
    except KeyboardInterrupt:
        graceful_shutdown(udp_client, udp_socket, tcp_socket, stop_event)

def graceful_shutdown(udp_client, udp_socket, tcp_socket, stop_event: threading.Event) -> None:
    '''
    Shuts down the client gracefully, ensuring all threads are stopped and sockets are closed.
    '''
    print("\nGraceful shutdown initiated...")
    stop_event.set()
    if udp_client:
        if udp_client.heartbeat_thread and udp_client.heartbeat_thread.is_alive():
            udp_client.heartbeat_thread.join()
        if udp_client.tcp_server_thread and udp_client.tcp_server_thread.is_alive():
            udp_client.tcp_server_thread.join()
    udp_socket.close()
    tcp_socket.close()
    print('Client shutdown complete.')
    sys.exit(0)

# ==============================================================================
# UDP Client
# ==============================================================================
class UDP_Client:
    '''
    Manages the client's connection to the server for authentication
    and interaction with other peers. Supports publishing, searching,
    and downloading files in the network.
    '''
    def __init__(self, udp_server_address: Tuple[str, int], udp_socket: socket.socket,
                 tcp_socket, tcp_listening_port: int, stop_event: threading.Event):
        self.server_address = udp_server_address
        self.udp_socket = udp_socket
        self.tcp_socket = tcp_socket
        self.tcp_listening_port = tcp_listening_port
        self.tcp_server_thread: Optional[TCPServer] = None
        self.stop_event = stop_event
        self.username: Optional[str] = None
        self.heartbeat_thread: Optional[Heartbeat_Thread] = None

    def start(self) -> None:
        '''
        Begins user input loop and initiates authentication with the server.
        Starts heartbeat after successful login.
        '''
        self.tcp_server_thread = TCPServer(self.tcp_socket, self.stop_event)
        self.tcp_server_thread.start()
        authenticated = False
        try:
            while not authenticated:
                username_tmp = input("Enter username: ")
                password = input("Enter password: ")
                request = f"login {username_tmp} {password} {self.tcp_listening_port}"
                self.udp_socket.sendto(request.encode('utf-8'), self.server_address)
                response, _ = self.udp_socket.recvfrom(BUFFER_SIZE)

                # Print the success/failure response from server
                print(response.decode('utf-8'))
                if response.decode('utf-8') == 'Welcome to BitTrickle!':
                    authenticated = True
                    self.username = username_tmp

            # Start heartbeat thread after successful authentication
            self.heartbeat_thread = Heartbeat_Thread(self.server_address,
                self.udp_socket, self.stop_event, self.username)
            self.heartbeat_thread.start()
            self.handle_commands()
        except KeyboardInterrupt:
            graceful_shutdown(self, self.udp_socket, self.tcp_socket, self.stop_event)
        except Exception as e:
            print(f"Error during authentication: {e}")

    def handle_commands(self) -> None:
        '''
        Command handler for user inputs, enabling operations like file publishing,
        searching, and downloading files from other peers.
        '''
        print("Available commands are: get, lap, lpf, pub, sch, unp, xit")
        command_funcs = {
            "get": self.get, "lap": self.lap, "lpf": self.lpf, "pub": self.pub,
            "sch": self.sch, "unp": self.unp,
        }

        try:
            while not self.stop_event.is_set():
                command = input("> ").strip()
                if not command:
                    continue

                if command.startswith("xit"):
                    print(f"Client {self.username} exiting gracefully...")
                    graceful_shutdown(self, self.udp_socket, self.tcp_socket, self.stop_event)
                    break

                command_parts = command.split(maxsplit=1)
                command_name = command_parts[0]
                args = command_parts[1] if len(command_parts) > 1 else ""
                func = command_funcs.get(command_name)
                if func:
                    func(args)
                else:
                    print("Unknown command")
        except KeyboardInterrupt:
            graceful_shutdown(self, self.udp_socket, self.tcp_socket, self.stop_event)

    def send_request_and_receive_response(self, request: str) -> None:
        '''Helper function to send a request to the server and print the response.'''
        self.udp_socket.sendto(request.encode(), self.server_address)
        try:
            response, _ = self.udp_socket.recvfrom(BUFFER_SIZE)
            print(response.decode('utf-8'))
        except (socket.error, OSError) as e:
            print(f"Error receiving server response: {e}")
        except KeyboardInterrupt:
            graceful_shutdown(self, self.udp_socket, self.tcp_socket, self.stop_event)

    def lap(self, args: str) -> None:
        '''Requests a list of active peers. Request: lap <username>'''
        if not args:
            self.send_request_and_receive_response(f"lap {self.username}")
        else:
            print("Error, usage: lap")

    def lpf(self, args: str) -> None:
        '''
        Requests a list of files published by the user. Request: lpf <username>
        lpf shows one client's published files regardless of his/her active/inactive status
         "what have I shared?"
        '''
        if not args:
            self.send_request_and_receive_response(f"lpf {self.username}")
        else:
            print("Error, usage: lpf")

    def pub(self, args: str) -> None:
        '''Publishes a specified file to the network. Request: pub <username> <filename>'''
        if len(args.split()) == 1:
            filename = args

            #Files are assumed to exist on current working directory
            if not os.path.isfile(filename):
                print(f"Error: File '{filename}' does not exist in the current directory.")
                return
            self.send_request_and_receive_response(f"pub {self.username} {filename}")
        else:
            print("Error, usage: pub <filename>")

    def unp(self, args: str) -> None:
        '''Unpublishes a specified file from the network. Request: unp <username> <filename>'''
        if len(args.split()) == 1:
            filename = args
            self.send_request_and_receive_response(f"unp {self.username} {filename}")
        else:
            print("Error, usage: unp <filename>")

    def sch(self, args: str) -> None:
        '''
        Request: sch <username> <substring>
        Searches for files with a specified substring in their names.
        "what can I download?" show what's actually available for download right now
        '''
        if len(args.split()) == 1:
            substring = args
            self.send_request_and_receive_response(f"sch {self.username} {substring}")
        else:
            print("Error, usage: sch <substring>")

    def get(self, args: str) -> None:
        '''
        Request: get <username> <filename>
        Requests a file download from a peer based on the filename.
        '''
        if len(args.split()) == 1:
            filename = args
            self.udp_socket.sendto(f"get {self.username} {filename}".encode(), self.server_address)
            try:
                response, _ = self.udp_socket.recvfrom(BUFFER_SIZE)
                response_split = response.decode('utf-8').split()
                if response_split[0] == '200':
                    tcp_ip = response_split[1]
                    tcp_port = int(response_split[2])
                    print(f"Requesting {filename} download from peer {tcp_ip}:{tcp_port}")
                    self.handle_tcp_request_and_download_file(tcp_ip, tcp_port, filename)
                else:
                    print(response.decode('utf-8'))
            except (socket.error, OSError) as e:
                print(f"Error receiving server response: {e}")
            except KeyboardInterrupt:
                graceful_shutdown(self, self.udp_socket, self.tcp_socket, self.stop_event)
        else:
            print("Error, usage: get <filename>")

    def handle_tcp_request_and_download_file(self, tcp_ip: str,
                                             server_port: int, filename: str) -> None:
        '''
        Downloads a file from a peer using TCP. Request a file download from a peer using TCP.
        '''
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
                client_socket.connect((tcp_ip, server_port))
                client_socket.sendall(filename.encode())
                with open(filename, 'wb') as file:
                    while True:
                        chunk = client_socket.recv(BUFFER_SIZE)
                        if not chunk:
                            break
                        file.write(chunk)
                print(f"File {filename} 100% downloaded successfully, "
                      "check your current working directory ✅")
        except ConnectionResetError:
            print(f"Connection reset by server {tcp_ip}:{server_port}")
        except (socket.error, OSError) as e:
            print(f"Error during file download from {tcp_ip}:{server_port} - {e}")
        except KeyboardInterrupt:
            graceful_shutdown(self, self.udp_socket, self.tcp_socket, self.stop_event)

# ==============================================================================
# Heartbeat
# ==============================================================================
class Heartbeat_Thread(threading.Thread):
    '''
    Thread that sends periodic heartbeat messages to the server,
    keeping the client marked as active.
    '''
    HEARTBEAT_INTERVAL: int = 2

    def __init__(self, server_address: Tuple[str, int], udp_socket: socket.socket,
                 stop_event: threading.Event, username: str):
        ''' Initializes the heartbeat thread with server details and stop event.'''
        super().__init__()
        self.server_address = server_address
        self.udp_socket = udp_socket
        self.stop_event = stop_event
        self.username = username

    def run(self) -> None:
        '''
        sendto: heartbeat username
        Sends heartbeat messages to the server until the stop event is set.
        '''
        while not self.stop_event.is_set():
            try:
                heartbeat_message = f"heartbeat {self.username}"
                self.udp_socket.sendto(heartbeat_message.encode(), self.server_address)
                time.sleep(self.HEARTBEAT_INTERVAL)
            except (socket.error, OSError):
                print("Error sending heartbeat. Retrying...")
        print("Heartbeat thread terminated.")

# ==============================================================================
# TCP Server
# ==============================================================================
class TCPServer(threading.Thread):
    '''
    Multi-threaded TCP server that listens for and handles file download requests from peers.
    '''
    THREAD_WORKERS: int = 5 # For the purpose of the assignment - 5 is enough

    def __init__(self, tcp_socket: socket.socket, stop_event: threading.Event):
        super().__init__()
        self.tcp_socket = tcp_socket
        self.stop_event = stop_event
        self.executor = ThreadPoolExecutor(max_workers=self.THREAD_WORKERS)

    def run(self) -> None:
        '''Listens for incoming file download requests from peers.'''
        self.tcp_socket.listen()
        while not self.stop_event.is_set():
            try:
                # Set timeout to allow stop_event check
                self.tcp_socket.settimeout(1)
                connection_socket, tcp_client_address = self.tcp_socket.accept()
                self.executor.submit(self.client_thread_handler, connection_socket, tcp_client_address)
            except socket.timeout:
                continue
        self.executor.shutdown(wait=True)
        print("⚡ TCP download listener terminated ⚡")

    def client_thread_handler(self, connection_socket: socket.socket,
                              tcp_client_address: Tuple[str, int]) -> None:
        '''Handles a file download request by sending the requested file in chunks.'''
        try:
            with connection_socket:
                filename = connection_socket.recv(BUFFER_SIZE).decode()
                with open(filename, 'rb') as file:
                    while chunk := file.read(BUFFER_SIZE):
                        connection_socket.sendall(chunk)
        except FileNotFoundError:
            connection_socket.sendall(b"Error: File not found")
        except ConnectionResetError:
            print(f"Connection reset by client {tcp_client_address}")
        except Exception as e:
            print(f"Error handling client {tcp_client_address}: {e}")

# ==============================================================================
# Main Entry
# ==============================================================================

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nMain program interrupted. Shutting down gracefully...")

################################################################################



