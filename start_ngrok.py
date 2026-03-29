from pyngrok import ngrok
import time

try:
    public_url = ngrok.connect(5000)
    print("=" * 50)
    print(f"YOUR PUBLIC URL: {public_url}")
    print("=" * 50)
    print("Press Ctrl+C to quit")
    while True:
        time.sleep(1)
except ImportError:
    print("Please install pyngrok: pip install pyngrok")
except Exception as e:
    print(f"Error starting ngrok: {e}")
