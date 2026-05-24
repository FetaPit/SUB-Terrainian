import sys
import requests

def get_lyrics(artist, song):
    url = f"https://lyrics.ovh{artist}/{song}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json().get("lyrics", "❌ Lyrics field empty.")
        return "❌ Lyrics not found. Check spelling."
    except Exception as e:
        return f"❌ Error: {e}"

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("💡 Usage: python scrape_lyrics.py 'Artist' 'Song'")
        sys.exit(1)
    
    print(f"\n🔍 Fetching: {sys.argv[2]} by {sys.argv[1]}...\n")
    print(get_lyrics(sys.argv[1], sys.argv[2]))
