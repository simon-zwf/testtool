import socket
import time
import xml.etree.ElementTree as ET


class SonosPlayer:
    def __init__(self, speaker_ip="169.254.201.46"):
        self.speaker_ip = speaker_ip

    def send_soap_command(self, service, action, body_params):
        """发送SOAP命令 - 使用正确的格式"""
        # 使用成功的SOAP格式
        soap_body = f'''<?xml version="1.0" encoding="utf-8"?><s:Envelope s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><ns0:{action} xmlns:ns0="urn:schemas-upnp-org:service:{service}:1">{body_params}</ns0:{action}></s:Body></s:Envelope>'''

        http_request = f"""POST /MediaRenderer/{service}/Control HTTP/1.1
Host: {self.speaker_ip}:1400
Content-Type: text/xml; charset="utf-8"
SOAPACTION: "urn:schemas-upnp-org:service:{service}:1#{action}"
Content-Length: {len(soap_body)}

{soap_body}"""

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((self.speaker_ip, 1400))
            sock.send(http_request.replace('\n', '\r\n').encode())

            response = b""
            sock.settimeout(5)
            try:
                while True:
                    chunk = sock.recv(1024)
                    if not chunk:
                        break
                    response += chunk
            except socket.timeout:
                pass

            sock.close()
            return response.decode('utf-8', errors='ignore')

        except Exception as e:
            return f"Error: {e}"

    def set_av_transport_uri(self, uri):
        """设置AV传输URI"""
        body_params = f"<InstanceID>0</InstanceID><CurrentURI>{uri}</CurrentURI><CurrentURIMetaData />"
        response = self.send_soap_command("AVTransport", "SetAVTransportURI", body_params)
        return "SetAVTransportURIResponse" in response

    def play(self):
        """播放"""
        body_params = "<InstanceID>0</InstanceID><Speed>1</Speed>"
        response = self.send_soap_command("AVTransport", "Play", body_params)
        return "PlayResponse" in response

    def pause(self):
        """暂停"""
        body_params = "<InstanceID>0</InstanceID>"
        response = self.send_soap_command("AVTransport", "Pause", body_params)
        return "PauseResponse" in response

    def stop(self):
        """停止"""
        body_params = "<InstanceID>0</InstanceID>"
        response = self.send_soap_command("AVTransport", "Stop", body_params)
        return "StopResponse" in response

    def set_volume(self, volume):
        """设置音量"""
        body_params = f"<InstanceID>0</InstanceID><Channel>Master</Channel><DesiredVolume>{volume}</DesiredVolume>"
        response = self.send_soap_command("RenderingControl", "SetVolume", body_params)
        return "SetVolumeResponse" in response

    def get_volume(self):
        """获取音量"""
        body_params = "<InstanceID>0</InstanceID><Channel>Master</Channel>"
        response = self.send_soap_command("RenderingControl", "GetVolume", body_params)

        try:
            # 解析XML获取音量值
            xml_part = response.split('\r\n\r\n', 1)[1]
            root = ET.fromstring(xml_part)
            for elem in root.iter():
                if 'CurrentVolume' in elem.tag:
                    return int(elem.text)
        except:
            pass
        return None

    def get_transport_info(self):
        """获取传输状态"""
        body_params = "<InstanceID>0</InstanceID>"
        response = self.send_soap_command("AVTransport", "GetTransportInfo", body_params)

        try:
            xml_part = response.split('\r\n\r\n', 1)[1]
            root = ET.fromstring(xml_part)
            for elem in root.iter():
                if 'CurrentTransportState' in elem.tag:
                    return elem.text
        except:
            pass
        return None

    def play_audio_file(self, file_path):
        """播放音频文件"""
        print(f"播放: {file_path}")

        # 使用localhost URI格式
        uri = f"http://localhost:1400{file_path}"

        # 设置URI
        if self.set_av_transport_uri(uri):
            print("✅ URI设置成功")

            # 等待一下
            time.sleep(1)

            # 播放
            if self.play():
                print("✅ 播放命令发送成功")
                return True
            else:
                print("❌ 播放命令失败")
                return False
        else:
            print("❌ URI设置失败")
            return False


# 完整的演示
def main():
    player = SonosPlayer("169.254.171.88")

    print("=== Sonos音响控制演示 ===")

    # 显示当前状态
    current_volume = player.get_volume()
    current_state = player.get_transport_info()
    print(f"当前音量: {current_volume}")
    print(f"当前状态: {current_state}")

    # 设置合适的音量
    print("\n设置音量为40...")
    if player.set_volume(40):
        print("✅ 音量设置成功")

    # 测试播放文件
    test_files = [
        "/pub/test.wav",  # 已知存在的文件
        "/pub/xiyangyang.wav",  # 你的文件
        "/pub/BB2013Crest7p5dB2Minutes.wav"  # 你的文件
    ]

    for file_path in test_files:
        print(f"\n=== 尝试播放 {file_path} ===")

        if player.play_audio_file(file_path):
            print("✅ 播放流程成功!")

            # 监控播放状态
            for i in range(5):
                time.sleep(2)
                status = player.get_transport_info()
                print(f"   播放状态 {i + 1}: {status}")

                if status == "PLAYING":
                    print("🎵 ✅ 确认音响正在播放!")

                    # 播放5秒后暂停
                    if i == 2:
                        print("暂停播放...")
                        player.pause()
                        time.sleep(2)
                        print("继续播放...")
                        player.play()
                    break
                elif status == "STOPPED":
                    print("❌ 播放停止")
                    break
        else:
            print("❌ 播放失败")

    print("\n=== 演示完成 ===")


if __name__ == "__main__":
    main()