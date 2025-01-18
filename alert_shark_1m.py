def test_display():
    """Test function to display crypto price status without Twitter posting"""
    import requests
    import json
    
    # Constants and API endpoints
    BTC_ATH = 1000000
    COINGECKO_API = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd"
    CRYPTOCOMPARE_API = "https://min-api.cryptocompare.com/data/pricemulti?fsyms=BTC,ETH&tsyms=USD"
    COINSTATS_API = "https://api.coinstats.app/public/v1/markets?coinId="

    def get_btc_price():
        try:
            # Try CoinGecko first
            response = requests.get(COINGECKO_API, timeout=10)
            response.raise_for_status()
            return float(response.json()["bitcoin"]["usd"])
        except Exception as e:
            print(f"Error fetching from CoinGecko: {e}")
            try:
                # Try CryptoCompare as backup
                response = requests.get(CRYPTOCOMPARE_API, timeout=10)
                response.raise_for_status()
                return float(response.json()["BTC"]["USD"])
            except Exception as e:
                print(f"Error fetching from CryptoCompare: {e}")
                try:
                    # Try CoinStats as final backup
                    response = requests.get(COINSTATS_API + "bitcoin", timeout=10)
                    response.raise_for_status()
                    return float(response.json()["pairs"][0]["price"])
                except Exception as e:
                    print(f"Error fetching from CoinStats: {e}")
                    return 0.0

    def get_eth_price():
        try:
            # Try CoinGecko first
            response = requests.get(COINGECKO_API, timeout=10)
            response.raise_for_status()
            return float(response.json()["ethereum"]["usd"])
        except Exception as e:
            print(f"Error fetching from CoinGecko: {e}")
            try:
                # Try CryptoCompare as backup
                response = requests.get(CRYPTOCOMPARE_API, timeout=10)
                response.raise_for_status()
                return float(response.json()["ETH"]["USD"])
            except Exception as e:
                print(f"Error fetching from CryptoCompare: {e}")
                try:
                    # Try CoinStats as final backup
                    response = requests.get(COINSTATS_API + "ethereum", timeout=10)
                    response.raise_for_status()
                    return float(response.json()["pairs"][0]["price"])
                except Exception as e:
                    print(f"Error fetching from CoinStats: {e}")
                    return 0.0
            
    def get_progress_bar(percentage):
        filled = min(int(percentage / 10), 10)
        bar = "⬛" * filled + "⬜" * (10 - filled)
        if percentage % 10 == 0 and percentage <= 100:
            marker_position = int(percentage / 10) - 1
            if marker_position >= 0:
                bar = bar[:marker_position] + "🟥" + bar[marker_position + 1:]
        return f"{bar} {percentage:.0f}%"

    # Fetch current prices
    btc_price = get_btc_price()
    eth_price = get_eth_price()
    
    if btc_price == 0 or eth_price == 0:
        print("Error fetching prices")
        return None
        
    # Calculate metrics
    percentage = (btc_price / BTC_ATH) * 100
    eth_btc_ratio = eth_price / btc_price
    
    # Build status message
    status = f"Bitcoin ↔ +0.00%\n\n"
    status += f"{get_progress_bar(percentage)}\n\n"
    status += f"${btc_price:,.2f}        eth/btc: {eth_btc_ratio:.2f}"
    
    # Print for debugging
    print("\nTest Display Output:")
    print(status)
    
    return status

if __name__ == "__main__":
    test_display()
