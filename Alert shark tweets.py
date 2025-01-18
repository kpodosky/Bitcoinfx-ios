import time
import tweepy
import logging
from alert_shark_1m import test_display
from Block_alert import BitcoinWhaleTracker
from keys import consumer_key, consumer_secret, access_token, access_token_secret

class TwitterBot:
    def __init__(self):
        # Match Alert_shark.py authentication method
        auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
        auth.set_access_token(access_token, access_token_secret)
        self.api = tweepy.API(auth, wait_on_rate_limit=True)
        
        # Test authentication
        try:
            self.api.verify_credentials()
            print("Authentication OK")
        except Exception as e:
            print("Error during authentication:", str(e))
            raise
            
        self.whale_tracker = BitcoinWhaleTracker(min_btc=100)
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger('TwitterBot')

    def post_tweet(self, message):
        try:
            # Use update_status instead of v2 endpoint
            tweet = self.api.update_status(status=message)
            self.logger.info(f"Tweet posted successfully with id: {tweet.id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to tweet: {e}")
            return False

    def check_price_update(self):
        """Run and post price status from alert_shark_1m.py"""
        try:
            if status := test_display():
                return self.post_tweet(status)
        except Exception as e:
            self.logger.error(f"Error in price update: {e}")
        return False

    def check_whale_alert(self):
        """Run and post whale alerts from Block_alert.py"""
        try:
            block_hash = self.whale_tracker.get_latest_block()
            if block_hash:
                txs = self.whale_tracker.get_block_transactions(block_hash)
                for tx in txs:
                    if processed_tx := self.whale_tracker.process_transaction(tx):
                        btc_price = self.whale_tracker.get_btc_price()
                        usd_value = processed_tx['btc_volume'] * btc_price
                        message = (
                            f"🚨 {processed_tx['tx_type']}\n"
                            f"{processed_tx['btc_volume']:.2f} BTC (${usd_value:,.2f})\n"
                            f"From: {self.whale_tracker.get_entity_name(processed_tx['sender'])}\n"
                            f"To: {self.whale_tracker.get_entity_name(processed_tx['receiver'])}"
                        )
                        return self.post_tweet(message)
        except Exception as e:
            self.logger.error(f"Error in whale alert: {e}")
        return False

    def run(self):
        self.logger.info("Starting Twitter Bot...")
        while True:
            try:
                # Run price update and wait before tweeting
                self.logger.info("Fetching price update...")
                status = test_display()
                if status:
                    self.logger.info("Waiting 2 minutes before posting price update...")
                    time.sleep(120)  # Wait 2 minutes before posting
                    self.post_tweet(status)

                # Wait another 2 minutes before checking whale alerts
                self.logger.info("Waiting 2 minutes before checking whale alerts...")
                time.sleep(120)

                # Check for whale alerts
                self.logger.info("Checking whale alerts...")
                if self.check_whale_alert():
                    # If whale alert was posted, wait 2 minutes
                    self.logger.info("Whale alert posted, waiting 2 minutes...")
                    time.sleep(120)
                else:
                    # If no whale alert, wait 3 minutes
                    self.logger.info("No whale activity, waiting 3 minutes...")
                    time.sleep(180)

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")
                time.sleep(30)

if __name__ == "__main__":
    bot = TwitterBot()
    bot.run()