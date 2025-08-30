#!/usr/bin/env python3
# -*- coding:utf-8 -*-

'''
Filename: server.py
Usage: python3 ../server.py 63155 <run where credentials.txt lives>

COMP3331/9331 Computer Networks and Applications Assignment
Bitrickle: a permissioned, peer-to-peer file sharing system with a centralised
indexing server.

The server authenticates users who wish to join the peer-to-peer network, keeps
track of which users store what files, and provides support services for users
to search for files and to connect to one another and transfer those files directly.

3 Data Structure
    1. Mapping username -> password for authentication
        self.credentials

    2. Mapping username -> upd_client address
        (gets updated during re-login, removed during inactive)

        self.active_clients[username] = {
            "udp_address": client_address,
            "last_heartbeat": time.time(),
            "tcp_address": (client_address[0], tcp_port)
        }

    3. Mapping Filename -> Username
        self.published_files[filename] = set()
'''

import argparse
from pathlib import Path
import socket
import sys
import time
from datetime import datetime
import re
from typing import Dict, Set, Tuple, Any

def main() -> None:
    '''
    Main function to initialize the server.
    Parses server port input, and start an instance of a UDP client server.
    '''
    if len(sys.argv) != 2:
        sys.exit("Usage: python3 server.py <server_port>")
    parser = argparse.ArgumentParser(description="UDP Server for handling P2P services")

    ''' Use a random port number between 49152 and 65535 (dynamic port number range).'''
    parser.add_argument('server_port', type=int, help='UDP port of the server')
    args = parser.parse_args()
    server = UDP_Server('127.0.0.1', args.server_port)
    server.run()

def load_credentials() -> Dict[str, str]:
    '''Load user credentials from credentials.txt, contains the usernames and passwords'''
    credentials = {}
    if not Path('credentials.txt').is_file():
        sys.exit("Error: credentials.txt does not exist.")
    with open('credentials.txt', 'r') as file:
        for line in file:
            if line.strip():
                username, password = line.strip().split()
                credentials[username] = password
    return credentials

# ==============================================================================
# UDP Server
# ==============================================================================
class UDP_Server:
    HEARTBEAT_TIMEOUT: int = 3                  # seconds
    RATE_LIMIT: float = 0.1                     # Rate limit for each client in seconds.
    BUFFER_SIZE: int = 1024                     # Size of the buffer for receiving messages.

    def __init__(self, server_host: str, server_port: int):
        self.server_host: str = server_host
        self.server_port: int = server_port
        self.server_socket: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server_socket.bind((server_host, server_port))
        print(f"⚡ Bitrickle Server started! Ready to receive on {self.server_host}:{self.server_port} ⚡")

        ''' Data Structure for Bittrickle'''
        self.credentials: Dict[str, str] = load_credentials()   # Stores credentials.txt
        self.active_clients: Dict[str, Dict[str, Any]] = {}     # Updated with each heartbeat
        self.published_files: Dict[str, Set[str]] = {}          # Stores published files from client

    # --------------------------------------------------------------------------
    def run(self) -> None:
        '''The main server loop, where the server listens for incoming requests.'''
        try:
            while True:
                try:
                    request, client_address = self.server_socket.recvfrom(self.BUFFER_SIZE)
                    self.check_client_activity()
                    self.handle_client_request(request.decode(), client_address)
                except (socket.error, OSError):
                    continue
        except KeyboardInterrupt:
            print('\nGraceful shutdown initiated...')
            self.server_socket.close()
            print('⚡ Bitrickle Server shutdown complete ⚡')

    # --------------------------------------------------------------------------
    def handle_client_request(self, request: str, client_address: Tuple[str, int]) -> None:
        '''Parse and handle client requests, mapping to the appropriate handler.'''
        parts = request.split()
        command = parts[0]
        command_map = {
            "login": (self.handle_login, 4),            # login username password tcp_port
            "heartbeat": (self.handle_heartbeat, 2),    # heartbeat username
            "lap": (self.handle_lap, 2),                # lap username
            "pub": (self.handle_pub, 3),                # pub username <filename>
            "unp": (self.handle_unp, 3),                # unp username <filename>
            "lpf": (self.handle_lpf, 2),                # lpf username
            "sch": (self.handle_sch, 3),                # sch username <substring>
            "get": (self.handle_get, 3)                 # get username <filename>
        }
        if command in command_map and len(parts) == command_map[command][1]:
            try:
                command_map[command][0](client_address, *parts[1:])
            except Exception as e:
                print(f"Error handling command '{command}': {e}")

    # --------------------------------------------------------------------------
    def check_client_activity(self) -> None:
        '''Remove inactive clients based on heartbeat timeout.'''
        current_time = time.time()
        to_remove = [
            username for username, client_info in self.active_clients.items()
            if current_time - client_info['last_heartbeat'] > self.HEARTBEAT_TIMEOUT
        ]
        for username in to_remove:
            client_address = self.active_clients[username]["udp_address"]
            self.log_message(client_address, f"Client {username} inactive ❌")
            del self.active_clients[username]

    def handle_heartbeat(self, client_address: Tuple[str, int], username: str) -> None:
        '''Update client's last active timestamp on receiving a heartbeat.'''
        if username in self.active_clients:
            self.active_clients[username]['last_heartbeat'] = time.time()
            self.log_message(client_address, f"Received HBT from {username}")

    # --------------------------------------------------------------------------
    def log_message(self, client_address: Tuple[str, int], message: str) -> None:
        '''Log a timestamped message to the console.'''
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        print(f"{timestamp}: {client_address} {message}")

    def send_response(self, client_address: Tuple[str, int], message: str) -> None:
        '''Send a response message to a client.'''
        try:
            self.server_socket.sendto(message.encode(), client_address)
        except (socket.error, OSError) as e:
            print(f"Error sending response: {e}")

    def send_error(self, client_address: Tuple[str, int], message: str) -> None:
        '''Send an error message to a client.'''
        self.send_response(client_address, f"Error: {message}")

    # --------------------------------------------------------------------------
    def handle_login(self, client_address: Tuple[str, int],
                     username: str, password: str, tcp_port: str) -> None:
        '''Client authenticate with server before issuing any command'''
        self.log_message(client_address, f"Received AUTH from {username}")

        # Case 1: The username is unknown
        if username not in self.credentials:
            response = "Authentication failed: Unknown username ❌."
            self.server_socket.sendto(response.encode(), client_address)
            self.log_message(client_address,
                f"Sent ERR - LOGIN to {username} ❌ - Unknown username.")
            return

        # Case 2: The username is known, but the password does not match
        if self.credentials[username] != password:
            response = "Authentication failed: Incorrect password. Please try again ❌."
            self.server_socket.sendto(response.encode(), client_address)
            self.log_message(client_address,
                f"Sent ERR - LOGIN to {username} ❌ - Incorrect password.")
            return

        # Case 3: The user is currently active
        if username in self.active_clients:
            response = "Authentication failed: User is already active ❌."
            self.server_socket.sendto(response.encode(), client_address)
            self.log_message(client_address,
                f"Sent ERR - LOGIN to {username} ❌ - User is already active.")
            return

        # If all checks pass, authenticate the user and store their info
        self.active_clients[username] = {
            "udp_address": client_address,
            "last_heartbeat": time.time(),
            "tcp_address": (client_address[0], tcp_port)
        }
        self.server_socket.sendto("Welcome to BitTrickle!".encode(), client_address)
        self.log_message(client_address, f"Sent OK - LOGIN to {username} ✅")

    # --------------------------------------------------------------------------
    def handle_lap(self, client_address: Tuple[str, int], username: str) -> None:
        '''
        Command at client: lap
        List all active peers excluding the requester.
        '''
        self.log_message(client_address, f"Received LAP from {username}")
        active_usernames = [user for user in self.active_clients if user != username]

        if not active_usernames:
            response = "No active peers available ❌."
        else:
            response = f"{len(active_usernames)} active peer(s):\n" + "\n".join(active_usernames)
        self.server_socket.sendto(response.encode(), client_address)
        self.log_message(client_address, f"Sent LAP - OK to {username} ✅")

    # --------------------------------------------------------------------------
    def handle_pub(self, client_address: Tuple[str, int], username: str, filename: str) -> None:
        '''
        Command at client: pub <filename>
        The client should inform the server that the user wishes to publish a file
        with the given name. File names are case sensitive. Files should remain
        published regardless of the user's active status.
        '''
        self.log_message(client_address, f"Received PUB from {username}")
        if filename not in self.published_files:
            self.published_files[filename] = set()

        if username in self.published_files[filename]:
            response = f"File '{filename}' is already published by you."
        else:
            self.published_files[filename].add(username)
            response = f"File '{filename}' published successfully."

        self.server_socket.sendto(response.encode(), client_address)
        self.log_message(client_address, f"Sent PUB - OK to {username} ✅")

    # --------------------------------------------------------------------------
    def handle_unp(self, client_address: Tuple[str, int], username: str, filename: str) -> None:
        '''
        Command at client: unp <filename>
        The client should inform the server that it wishes to unpublish a file
        '''
        self.log_message(client_address, f"Received UNP from {username}")

        # Filename doesn't exist
        if filename not in self.published_files or username not in self.published_files[filename]:
            response = (
                f"File '{filename}' unpublication failed. File doesn't "
                "exist or is already unpublished ❌."
            )
            self.log_message(client_address, f"Sent UNP - ERR to {username} ❌")
        else:
            # Remove the requester from the list of users who published the file
            self.published_files[filename].remove(username)

            # If no more users have published this file, remove the file entry
            if not self.published_files[filename]:
                del self.published_files[filename]

            response = f"File '{filename}' unpublished successfully."
            self.log_message(client_address, f"Sent UNP - OK to {username} ✅")
        self.server_socket.sendto(response.encode(), client_address)

    # --------------------------------------------------------------------------
    def handle_lpf(self, client_address: Tuple[str, int], username: str) -> None:
        '''
        Command at client: lpf
        The client query the server for a list of files that are currently
        published (i.e. shared) by the user and print out their names.
        '''
        self.log_message(client_address, f"Received LPF from {username}")

        # Collect the files published by this specific user
        active_files = [
            file for file, users in self.published_files.items()
            if username in users
        ]
        # Check if there are any active files published by the user
        if not active_files:
            response = "No files published ❌."
        else:
            response = f"{len(active_files)} file(s) published:\n" + "\n".join(active_files)
        # Send the response to the client
        self.server_socket.sendto(response.encode(), client_address)
        self.log_message(client_address, f"Sent LPF - OK to {username} ✅")

    # --------------------------------------------------------------------------
    def handle_sch(self, client_address: Tuple[str, int], username: str, substring: str) -> None:
        '''
        Command at client: sch <substring>
        Query the server for any files published by active peers that contain the substring.
        Only return files published by active peers, excluding files published by the requester.
        '''
        self.log_message(client_address, f"Received SCH from {username}")

        # Collect files that contain the substring
        queried_files = []
        for file, users in self.published_files.items():

            # If substring matches part of the substring - check the users
            if substring in file:

                # Skip this file if the requester (username) is in the set of publishers
                if username in users:
                    continue

                # Check if there are active peers other than requester
                other_active_users = False
                for u in users:
                    if u in self.active_clients and u != username:
                        other_active_users = True
                        break
                if other_active_users:
                    queried_files.append(file)


        # Prepare the response based on whether matching files were found
        if queried_files:
            response = f"{len(queried_files)} file(s) found:\n" + "\n".join(queried_files)
        else:
            response = "No files found ❌."

        # Send the response to the client
        self.server_socket.sendto(response.encode(), client_address)
        self.log_message(client_address, f"Sent SCH - OK to {username} ✅")

    # --------------------------------------------------------------------------
    def handle_get(self, client_address: Tuple[str, int], username: str, queried_filename: str) -> None:
        '''
        Command at client side: get <filename>
        Return the TCP address of peer who has the matching published filename
        If there are multiple such peers, the server (or client) may select one
        arbitrarily and return the TCP address of that peer.
        '''
        self.log_message(client_address, f"Received GET from {username}")

        if queried_filename in self.published_files:
            potential_active_peers = self.published_files[queried_filename]

            # If the peer already published the file, we return error
            if username in potential_active_peers:
                response = f"Error you already published this file '{queried_filename}' ❌."
                self.log_message(client_address, f"Sent GET - ERR to {username} ❌")
            else:
                # Find an active peer who has the file
                tcp_address_result = None
                for user in potential_active_peers:
                    if user in self.active_clients:
                        tcp_address_result = self.active_clients[user]["tcp_address"]
                        break

                # Send the TCP address to the requester if an active peer was found
                if tcp_address_result:
                    tcp_ip = tcp_address_result[0]
                    tcp_port = tcp_address_result[1]
                    response = f"200 {tcp_ip} {tcp_port}"
                    self.log_message(client_address, f"Sent GET - OK to {username} ✅")
                else:
                    # No active peers have the file
                    response = (
                        f"No active peers found with file '{queried_filename}' or you "
                        "already have the file published ❌."
                    )
                    self.log_message(client_address, f"Sent GET - ERR to {username} ❌")
        else:
            response = f"File '{queried_filename}' not found in published files ❌."
            self.log_message(client_address, f"Sent GET - ERR to {username} ❌")

        self.server_socket.sendto(response.encode(), client_address)

# ==============================================================================
# Main Entry
# ==============================================================================

if __name__ == '__main__':
    main()

################################################################################