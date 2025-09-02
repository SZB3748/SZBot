import soundplayer
import sys

if __name__ == "__main__":
    addr = sys.argv[1]
    player = soundplayer.SoundRequestPlayer(addr, addr.endswith(":443"), sys.argv[2] if len(sys.argv) > 2 else None)
    player.start()