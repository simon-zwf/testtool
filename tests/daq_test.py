import  socket
import  time
from http.client import responses
from datetime import datetime

DAQ_IP = "192.168.1.8"
DAQ_PORT = 5025


def simple_monitor():
    try:
        sock= socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((DAQ_IP, DAQ_PORT))
        print(f"connected successfully")

        try:
            sock.settimeout(0.1)
            while True:
                data = sock.recv(1024)
                if not data:
                    break
        except:
            pass
        finally:
            sock.settimeout(5)

        print(f"\n===starting to monitor the Voltage(use the command READ?)===")
        print(f"The current channel is configured for Voltage")
        print(f"Press Ctrl+C to stop")
        print(f"_" * 50)

        count = 0
        while True:
            try:
                sock.sendall(b"READ?\n")
                time.sleep(0.5)
                response = b""
                while True:
                    try:
                        data = sock.recv(1024)
                        if not data:
                            break
                        response += data
                        if b"\n" in data:
                            break
                    except sock.timeout:
                        break

                count += 1
                timestamp = datetime.now().strftime("%H:%M:%S")

                if response:
                    result = response.decode('ascii', errors='ignore').strip()
                    try:
                        voltage = float(result)
                        print(f"[{timestamp}] #{count}: {voltage:.6f} V")
                        if abs(voltage) > 0.1:
                            print(f"Note: Significant voltage detected ({voltage:.4f}) V")
                    except ValueError:
                        print(f"[{timestamp}] # {count}: received {result}")
                else:
                    print(f"[{timestamp}] #{count}: not response")
                time.sleep(2)

            except KeyboardInterrupt:
                print(f"\n stop monitor")
                break
            except Exception as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ERROR: {e}")
                time.sleep(1)

    except Exception as e:
        print(f"connect fail:{e}")

    finally:
        if 'sock' in locals():
            sock.close()
            print("connect close")


if __name__ == "__main__":
    print(f"DAQ970A simple monitor the voltage")
    print(f"=" * 50)
    simple_monitor()


