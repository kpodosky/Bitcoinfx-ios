# -*- coding: UTF-8 -*-
import requests
import time
import json
import re
from bs4 import BeautifulSoup
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Optional
import logging
from pathlib import Path
import threading
from keys import consumer_key, consumer_secret, access_token, access_token_secret, bearer_token
import tweepy

class TwitterPoster:
    def __init__(self, creds=None):
        # Setup authentication using imported keys
        auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
        auth.set_access_token(access_token, access_token_secret)
        
        # Initialize API v1.1 for media uploads
        self.api = tweepy.API(auth)
        
        # Initialize v2 client
        self.client = tweepy.Client(
            bearer_token=bearer_token,
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            access_token=access_token,
            access_token_secret=access_token_secret,
            wait_on_rate_limit=True
        )

class DOJAddressMonitor:
    def __init__(self, logger):
        self.logger = logger
        self.sources = {
            'forfeiture': {
                'url': 'https://www.justice.gov/criminal-mlars/equitable-sharing-program',
                'pattern': r'bc1[a-zA-Z0-9]{8,87}|[13][a-km-zA-HJ-NP-Z1-9]{25,34}'
            },
            'usao': {
                'url': 'https://www.justice.gov/usao/pressreleases',
                'pattern': r'bc1[a-zA-Z0-9]{8,87}|[13][a-km-zA-HJ-NP-Z1-9]{25,34}'
            }
        }
        
        self.address_history_file = Path('doj_address_history.json')
        self.load_history()
        
    def load_history(self):
        """Load address history from file"""
        try:
            with open(self.address_history_file, 'r') as f:
                self.address_history = json.load(f)
        except FileNotFoundError:
            self.address_history = {
                'last_update': None,
                'addresses': {}
            }

    def save_history(self):
        """Save address history to file"""
        with open(self.address_history_file, 'w') as f:
            json.dump(self.address_history, f, indent=4)

    def verify_bitcoin_address(self, address: str) -> bool:
        """Verify if a string is a valid Bitcoin address"""
        try:
            response = requests.get(f'https://blockchain.info/address/{address}')
            return response.status_code == 200
        except:
            return False

    def extract_case_info(self, text: str) -> Optional[Dict]:
        """Extract case information from text"""
        patterns = {
            'case_number': r'Case\s+(?:No\.?|Number:?)\s*([\w-]+)',
            'filing_date': r'Filed:?\s*(\w+\s+\d{1,2},\s*\d{4})',
            'district': r'(?:in\s+the\s+)?(\w+\s+District\s+(?:Court\s+)?of\s+[\w\s]+)',
            'amount': r'(?:BTC|Bitcoin)\s*(?:worth)?\s*(?:approximately)?\s*[$]?([\d,]+(?:\.\d{2})?)'
        }
        
        info = {}
        for key, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                info[key] = match.group(1)
        
        return info if info else None

    def scan_doj_page(self, url: str, pattern: str) -> List[Dict]:
        """Scan a DOJ page for Bitcoin addresses and related information"""
        try:
            response = requests.get(url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            found_addresses = []
            for text_block in soup.find_all(['p', 'div', 'td']):
                text = text_block.get_text()
                addresses = re.findall(pattern, text)
                
                for address in addresses:
                    if self.verify_bitcoin_address(address):
                        case_info = self.extract_case_info(text)
                        if case_info:
                            found_addresses.append({
                                'address': address,
                                'source_url': url,
                                'discovery_date': datetime.now().isoformat(),
                                **case_info
                            })
            
            return found_addresses
            
        except Exception as e:
            self.logger.error(f"Error scanning {url}: {str(e)}")
            return []

    def update_addresses(self) -> Dict[str, List[str]]:
        """Update DOJ addresses from all sources"""
        all_new_addresses = {
            'forfeiture': [],
            'usao': []
        }
        
        for source_type, source_info in self.sources.items():
            addresses = self.scan_doj_page(source_info['url'], source_info['pattern'])
            all_new_addresses[source_type].extend(addresses)
        
        # Update address history
        current_time = datetime.now().isoformat()
        for category, addresses in all_new_addresses.items():
            for addr_info in addresses:
                address = addr_info['address']
                if address not in self.address_history['addresses']:
                    self.address_history['addresses'][address] = addr_info
                    self.logger.info(f"New {category} address found: {address}")
        
        self.address_history['last_update'] = current_time
        self.save_history()
        
        return all_new_addresses

class BitcoinWhaleTracker:
    def __init__(self, min_btc=500):
        # Setup logging first
        self.logger = self._setup_logging()
        
        # Setup Twitter
        self.twitter = TwitterPoster()
        
        # Initialize basic tracking parameters
        self.base_url = "https://blockchain.info"
        self.min_btc = min_btc
        self.satoshi_to_btc = 100000000
        self.processed_blocks = set()
        self.last_block_height = None
        
        # Initialize DOJ monitor
        self.doj_monitor = DOJAddressMonitor(self.logger)
        
        # Address statistics tracking
        self.address_stats = defaultdict(lambda: {
            'received_count': 0,
            'sent_count': 0,
            'total_received': 0,
            'total_sent': 0,
            'last_seen': None
        })
        
        # Known addresses database
        self.known_addresses = {
            'binance': {
                'type': 'exchange',
                'addresses': [
                    '3FaA4dJuuvJFyUHbqHLkZKJcuDPugvG3zE',  # Binance Hot Wallet
                    '1NDyJtNTjmwk5xPNhjgAMu4HDHigtobu1s',  # Binance Cold Wallet
                    '34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo',  # Binance-BTC-2
                    '1LQv8aKtQoiY5M5zkaG8RWL7LMwNzNsLfb',  # Binance-BTC-3
                    '1AC4fMwgY8j9onSbXEWeH6Zan8QGMSdmtA'   # Binance-BTC-4
                ]
            },
            'coinbase': {
                'type': 'exchange',
                'addresses': [
                    '3FzScn724foqFRWvL1kCZwitQvcxrnSQ4K',  # Coinbase Hot Wallet
                    '3Kzh9qAqVWQhEsfQz7zEQL1EuSx5tyNLNS',  # Coinbase Cold Storage
                    '1CWYTCvwKfH5cWnX3VcAykgTsmjsuB3wXe',  # Coinbase-BTC-2
                    '1FxkfJQLJTXpW6QmxGT6hEo5DtBrnFpM3r',  # Coinbase-BTC-3
                    '1GR9qNz7zgtaW5HwwVpEJWMnGWhsbsieCG'   # Coinbase Prime
                ]
                  },
            'grayscale': {
                'type': 'investment',
                'addresses': [
                    'bc1qe7nps5yv7ruc884zscwrk9g2mxvqh7tkxfxwny',
                    'bc1qkz7u6l5c8wqz8nc5yxkls2j8u4y2hkdzlgfnl4'
                ]
            },
            'microstrategy': {
                'type': 'corporate',
                'addresses': [
                    'bc1qazcm763858nkj2dj986etajv6wquslv8uxwczt',
                    'bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh'
                ]
            },
            'blockfi': {
                'type': 'lending',
                'addresses': [
                    'bc1q7kyrfmx49qa7n6g8mvlh36d4w9zf4lkwfg4j5q',
                    'bc1qd73dxk2qfs2x5wv2sesvqrzgx7t5tqt4y5vpym'
                ]
            },
            'celsius': {
                'type': 'lending',
                'addresses': [
                    'bc1q06ymtp6eq27mlz3ppv8z7esc8vq3v4nsjx9eng',
                    'bc1qcex3e38gqh6qnzpn9jth5drgfyh5k9sjzq3rkm'
                ]
            },
            'kraken': {
                'type': 'exchange',
                'addresses': [
                    '3FupZp77ySr7jwoLYEJ9mwzJpvoNBXsBnE',  # Kraken Hot Wallet
                    '3H5JTt42K7RmZtromfTSefcMEFMMe18pMD',  # Kraken Cold Storage
                    '3AfP9N7KNq2pYXiGQdgNJy8SD2Mo7pQKUR',  # Kraken-BTC-2
                    '3E1jkR1PJ8hFUqCkDjimwPoF2bZVrkqnpv'   # Kraken-BTC-3
                ]
            },
            'bitfinex': {
                'type': 'exchange',
                'addresses': [
                    '3D2oetdNuZUqQHPJmcMDDHYoqkyNVsFk9r',  # Bitfinex Hot Wallet
                    '3JZq4atUahhuA9rLhXLMhhTo133J9rF97j',  # Bitfinex Cold Storage
                    '3QW95MafxER9W7kWDcosQNdLk4Z36TYJZL'   # Bitfinex-BTC-2
                ]
            },
            'huobi': {
                'type': 'exchange',
                'addresses': [
                    '3M219KR5vEneNb47ewrPfWyb5jQ2DjxRP6',  # Huobi Hot Wallet
                    '38WUPqGLXphpD1DwkMR8koGfd5UQfRnmrk',  # Huobi Cold Storage
                    '1HckjUpRGcrrRAtFaaCAUaGjsPx9oYmLaZ'   # Huobi-BTC-2
                ]
            },
            'okex': {
                'type': 'exchange',
                'addresses': [
                    '3LQUu4v9z6KNch71j7kbj8GPeAGUo1FW6a',  # OKEx Hot Wallet
                    '3LCGsSmfr24demGvriN4e3ft8wEcDuHFqh',  # OKEx Cold Storage
                    '3FupZp77ySr7jwoLYEJ9mwzJpvoNBXsBnE'   # OKEx-BTC-2
                ]
            },
            'gemini': {
                'type': 'exchange',
                'addresses': [
                    '3P3QsMVK89JBNqZQv5zMAKG8FK3kJM4rjt',  # Gemini Hot Wallet
                    '393HLwqnkrJMxYQTHjWBJPAKC3UG6k6FwB',  # Gemini Cold Storage
                    '3AAzK4Xbu8PTM8AD7gw2XaMZavL6xoKWHQ'   # Gemini-BTC-2
                ]
            },
            'bitstamp': {
                'type': 'exchange',
                'addresses': [
                    '3P3QsMVK89JBNqZQv5zMAKG8FK3kJM4rjt',  # Bitstamp Hot Wallet
                    '3D2oetdNuZUqQHPJmcMDDHYoqkyNVsFk9r',  # Bitstamp Cold Storage
                    '3DbAZpqKhUBu4rqafHzj7hWquoBL6gFBvj'   # Bitstamp-BTC-2
                ]
            },
            'bittrex': {
                'type': 'exchange',
                'addresses': [
                    '3KJrsjfg1dD6CrsTeHdM5SSk3PhXjNwhA7',  # Bittrex Hot Wallet
                    '3KJrsjfg1dD6CrsTeHdM5SSk3PhXjNwhA7',  # Bittrex Cold Storage
                    '3QW95MafxER9W7kWDcosQNdLk4Z36TYJZL'   # Bittrex-BTC-2
                ]
            },
            'kucoin': {
                'type': 'exchange',
                'addresses': [
                    '3M219KR5vEneNb47ewrPfWyb5jQ2DjxRP6',  # KuCoin Hot Wallet
                    '3H5JTt42K7RmZtromfTSefcMEFMMe18pMD',  # KuCoin Cold Storage
                    '3AfP9N7KNq2pYXiGQdgNJy8SD2Mo7pQKUR'   # KuCoin-BTC-2
                ]
            },
            'gate_io': {
                'type': 'exchange',
                'addresses': [
                    '3FupZp77ySr7jwoLYEJ9mwzJpvoNBXsBnE',  # Gate.io Hot Wallet
                    '38WUPqGLXphpD1DwkMR8koGfd5UQfRnmrk',  # Gate.io Cold Storage
                ]
            },
            'ftx': {
                'type': 'exchange',
                'addresses': [
                    '3LQUu4v9z6KNch71j7kbj8GPeAGUo1FW6a',  # FTX Hot Wallet
                    '3E1jkR1PJ8hFUqCkDjimwPoF2bZVrkqnpv',  # FTX Cold Storage
                ]
            },
            'bybit': {
                'type': 'exchange',
                'addresses': [
                    '3JZq4atUahhuA9rLhXLMhhTo133J9rF97j',  # Bybit Hot Wallet
                    '3QW95MafxER9W7kWDcosQNdLk4Z36TYJZL',  # Bybit Cold Storage
                ]
            },
            'cryptocom': {
                'type': 'exchange',
                'addresses': [
                    '3P3QsMVK89JBNqZQv5zMAKG8FK3kJM4rjt',  # Crypto.com Hot Wallet
                    '3AAzK4Xbu8PTM8AD7gw2XaMZavL6xoKWHQ',  # Crypto.com Cold Storage
                ]
            },
            'doj': {
                'type': 'government',
                'addresses': []  # Will be populated by DOJ monitor
            }
        }
        
        # Start DOJ monitoring thread
        self.start_doj_monitor()

    def _setup_logging(self) -> logging.Logger:
        """Setup logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('whale_tracker.log'),
                logging.StreamHandler()
            ]
        )
        return logging.getLogger('WhaleTracker')

    def start_doj_monitor(self):
        """Start DOJ address monitoring in a separate thread"""
        def monitor_loop():
            while True:
                try:
                    self.logger.info("Updating DOJ addresses...")
                    new_addresses = self.doj_monitor.update_addresses()
                    
                    # Update known_addresses with new DOJ addresses
                    doj_addresses = []
                    for category, addresses in new_addresses.items():
                        for addr_info in addresses:
                            doj_addresses.append(addr_info['address'])
                    
                    self.known_addresses['doj']['addresses'] = list(set(
                        self.known_addresses['doj']['addresses'] + doj_addresses
                    ))
                    
                    self.logger.info(f"Found {len(doj_addresses)} new DOJ addresses")
                    time.sleep(21600)  # Update every 6 hours
                    
                except Exception as e:
                    self.logger.error(f"Error in DOJ monitor: {str(e)}")
                    time.sleep(300)  # Wait 5 minutes on error

        monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        monitor_thread.start()

    def get_latest_block(self):
        """Get the latest block hash and ensure we don't process duplicates"""
        try:
            response = requests.get(f"{self.base_url}/latestblock")
            block_data = response.json()
            current_height = block_data['height']
            current_hash = block_data['hash']
            
            if self.last_block_height is None:
                self.last_block_height = current_height
                return current_hash
                
            if current_hash in self.processed_blocks:
                return None
                
            if current_height > self.last_block_height:
                self.last_block_height = current_height
                if len(self.processed_blocks) > 1000:
                    self.processed_blocks.clear()
                self.processed_blocks.add(current_hash)
                self.logger.info(f"New Block: {current_height} | Hash: {current_hash[:8]}...")
                return current_hash
                
            return None
            
        except Exception as e:
            self.logger.error(f"Error getting latest block: {e}")
            return None

    def get_block_transactions(self, block_hash):
        """Get all transactions in a block"""
        try:
            response = requests.get(f"{self.base_url}/rawblock/{block_hash}")
            return response.json()['tx']
        except Exception as e:
            self.logger.error(f"Error getting block transactions: {e}")
            return []

    def get_address_label(self, address):
        """Get the entity label for an address with DOJ case information"""
        if address in self.known_addresses['doj']['addresses']:
            doj_info = self.doj_monitor.address_history['addresses'].get(address, {})
            return f"(DOJ - Case {doj_info.get('case_number', 'UNKNOWN')})"
            
        for entity, info in self.known_addresses.items():
            if address in info['addresses']:
                return f"({entity.upper()} {info['type']})"
        return ""

    def get_entity_name(self, address: str) -> str:
        """Get entity name for a known address or return 'UNKNOWN'"""
        for entity, info in self.known_addresses.items():
            if address in info['addresses']:
                return entity.upper()
        # If not found, return UNKNOWN instead of truncated address
        return "UNKNOWN"

    def get_btc_price(self) -> float:
        """Get current Bitcoin price in USD"""
        try:
            response = requests.get("https://api.coindesk.com/v1/bpi/currentprice/USD.json")
            return float(response.json()['bpi']['USD']['rate'].replace(',', ''))
        except Exception as e:
            self.logger.error(f"Error getting BTC price: {e}")
            return 0

    def print_transaction(self, tx):
        """Print transaction in the new format"""
        try:
            # Get BTC price
            btc_price = self.get_btc_price()
            btc_amount = float(tx['btc_volume'])
            usd_value = btc_amount * btc_price

            # Get sender and receiver names
            sender = self.get_entity_name(tx['sender'])
            receiver = self.get_entity_name(tx['receiver'])

            # Calculate fee in USD
            fee_btc = float(tx['fee_btc'])
            fee_usd = fee_btc * btc_price

            # Format the message
            message = (
                f"\n🚨🚨🚨 {tx['tx_type']} Transaction:\n"
                f"{btc_amount:.2f} #BTC (${usd_value:,.2f}) "
                f"was sent from {sender} "
                f"to {receiver}\n"
                f"and the transaction #fee was {fee_btc:.8f} BTC (${fee_usd:.2f})"
            )

            # Print with color based on transaction type
            color_code = {
                'DEPOSIT': '\033[92m',      # Green
                'WITHDRAWAL': '\033[91m',    # Red
                'DOJ TRANSFER': '\033[95m',  # Purple
                'INTERNAL TRANSFER': '\033[93m',  # Yellow
                'UNKNOWN TRANSFER': '\033[94m'    # Blue
            }.get(tx['tx_type'], '\033[94m')

            print(f"{color_code}{message}\033[0m")
            print("-" * 80)  # Separator line

        except Exception as e:
            self.logger.error(f"Error formatting transaction output: {e}")

    def process_transaction(self, tx):
        """Process a single transaction and return formatted data"""
        try:
            # Calculate total input value
            total_input = sum(inp.get('prev_out', {}).get('value', 0) for inp in tx.get('inputs', []))
            total_output = sum(out.get('value', 0) for out in tx.get('out', []))
            
            # Convert from satoshi to BTC
            btc_volume = total_input / self.satoshi_to_btc
            
            # Only process transactions above minimum BTC threshold
            if btc_volume >= self.min_btc:
                # Get the primary sender and receiver
                sender = tx['inputs'][0].get('prev_out', {}).get('addr', 'Unknown')
                receiver = tx['out'][0].get('addr', 'Unknown')
                
                # Calculate fee
                fee_btc = (total_input - total_output) / self.satoshi_to_btc
                
                # Determine transaction type
                tx_type = "alert #bitcoin"
                if sender in self.known_addresses['binance']['addresses'] or sender in self.known_addresses['coinbase']['addresses']:
                    tx_type = "witdrawal"
                elif receiver in self.known_addresses['binance']['addresses'] or receiver in self.known_addresses['coinbase']['addresses']:
                    tx_type = "deposit"
                elif sender in self.known_addresses['doj']['addresses'] or receiver in self.known_addresses['doj']['addresses']:
                    tx_type = "doj transfer"
                
                return {
                    'transaction_hash': tx.get('hash', 'Unknown'),
                    'timestamp': datetime.fromtimestamp(tx.get('time', 0)).strftime('%Y-%m-%d %H:%M:%S'),
                    'btc_volume': btc_volume,
                    'fee_btc': fee_btc,
                    'sender': sender,
                    'receiver': receiver,
                    'tx_type': tx_type
                }
                
        except Exception as e:
            self.logger.error(f"Error processing transaction: {e}")
            return None

    def track_whale_transactions(self):  # Fixed method name here
        """Main method to track whale transactions"""
        self.logger.info(f"Tracking Bitcoin transactions over {self.min_btc} BTC...")
        self.logger.info("Waiting for new blocks...")
        
        while True:
            try:
                block_hash = self.get_latest_block()
                
                if block_hash:
                    transactions = self.get_block_transactions(block_hash)
                    processed_count = 0
                    whale_count = 0
                    
                    for tx in transactions:
                        processed_count += 1
                        
                        # Calculate total input value
                        total_input = sum(inp.get('prev_out', {}).get('value', 0) for inp in tx.get('inputs', []))
                        
                        # Calculate total output value
                        total_output = sum(out.get('value', 0) for out in tx.get('out', []))
                        
                        # Convert from satoshi to BTC
                        btc_volume = total_input / self.satoshi_to_btc
                        
                        # Only process transactions above minimum BTC threshold
                        if btc_volume >= self.min_btc:
                            whale_count += 1
                            
                            # Get the primary sender (first input address)
                            sender = tx['inputs'][0].get('prev_out', {}).get('addr', 'Unknown')
                            
                            # Get the primary receiver (first output address)
                            receiver = tx['out'][0].get('addr', 'Unknown')
                            
                            # Calculate fee
                            fee_btc = (total_input - total_output) / self.satoshi_to_btc
                            
                            # Determine transaction type
                            tx_type = "UNKNOWN"
                            if sender in self.known_addresses['binance']['addresses'] or sender in self.known_addresses['coinbase']['addresses']:
                                tx_type = "WITHDRAWAL"
                            elif receiver in self.known_addresses['binance']['addresses'] or receiver in self.known_addresses['coinbase']['addresses']:
                                tx_type = "DEPOSIT"
                            elif sender in self.known_addresses['doj']['addresses'] or receiver in self.known_addresses['doj']['addresses']:
                                tx_type = "DOJ TRANSFER"
                            
                            # Create transaction record
                            whale_tx = {
                                'transaction_hash': tx.get('hash', 'Unknown'),
                                'timestamp': datetime.fromtimestamp(tx.get('time', 0)).strftime('%Y-%m-%d %H:%M:%S'),
                                'btc_volume': f"{btc_volume:.8f}",
                                'fee_btc': f"{fee_btc:.8f}",
                                'sender': sender,
                                'receiver': receiver,
                                'tx_type': tx_type
                            }
                            
                            # Print transaction details
                            self.print_transaction(whale_tx)
                            
                            # Update address statistics
                            self.address_stats[sender]['sent_count'] += 1
                            self.address_stats[sender]['total_sent'] += btc_volume
                            self.address_stats[sender]['last_seen'] = whale_tx['timestamp']
                            
                            self.address_stats[receiver]['received_count'] += 1
                            self.address_stats[receiver]['total_received'] += btc_volume
                            self.address_stats[receiver]['last_seen'] = whale_tx['timestamp']
                    
                    self.logger.info(f"Processed {processed_count} transactions, found {whale_count} whale movements")
                self.logger.info(f"Processed {processed_count} transactions, found {whale_count} whale movements")
                time.sleep(30)  # Check every 30 seconds
        
        
            except Exception as e:
              self.logger.error(f"Error in main loop: {e}")
              time.sleep(30)

if __name__ == "__main__":
    tracker = BitcoinWhaleTracker(min_btc=500)
    tracker.track_whale_transactions()