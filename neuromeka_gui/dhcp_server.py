import socket
import struct
import time

def parse_dhcp_pkt(data):
    if len(data) < 240:
        return None
    op, htype, hlen, hops, xid, secs, flags = struct.unpack('!BBBBIHH', data[:12])
    mac = data[28:34]
    mac_str = ':'.join(f'{b:02x}' for b in mac)
    
    # Parse DHCP message type from options
    msg_type = None
    options = data[240:]
    i = 0
    while i < len(options):
        opt = options[i]
        if opt == 255: # End
            break
        if opt == 0: # Pad
            i += 1
            continue
        if i + 1 >= len(options):
            break
        length = options[i + 1]
        if opt == 53 and length >= 1 and i + 2 < len(options):
            msg_type = options[i + 2]
        i += 2 + length

    return msg_type, xid, mac, mac_str

def make_dhcp_reply(msg_type, xid, mac, client_ip, server_ip):
    # Header: op=2 (REPLY), htype=1, hlen=6, hops=0, broadcast flag=0x8000
    hdr = struct.pack('!BBBBIHH', 2, 1, 6, 0, xid, 0, 0x8000)
    ciaddr = socket.inet_aton('0.0.0.0')
    yiaddr = socket.inet_aton(client_ip)
    siaddr = socket.inet_aton(server_ip)
    giaddr = socket.inet_aton('0.0.0.0')
    chaddr = mac + b'\x00' * 10
    sname = b'\x00' * 64
    file_spec = b'\x00' * 128
    cookie = b'\x63\x82\x53\x63'

    # Options
    opt_msgtype = struct.pack('!BBB', 53, 1, msg_type) # 2=OFFER, 5=ACK
    opt_serverid = b'\x36\x04' + socket.inet_aton(server_ip) # 54
    opt_lease = struct.pack('!BBI', 51, 4, 86400) # 51
    opt_mask = b'\x01\x04' + socket.inet_aton('255.255.255.0') # 1
    opt_router = b'\x03\x04' + socket.inet_aton(server_ip) # 3
    opt_end = b'\xff'

    options = opt_msgtype + opt_serverid + opt_lease + opt_mask + opt_router + opt_end
    return hdr + ciaddr + yiaddr + siaddr + giaddr + chaddr + sname + file_spec + cookie + options

def run_dhcp_server(server_ip='192.168.137.1', assigned_ip='192.168.137.100', timeout_sec=20):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(('0.0.0.0', 67))
    sock.settimeout(1.0)

    print(f"[DHCP SERVER ENGINE] Active on 0.0.0.0:67 (Server IP: {server_ip}, Target: {assigned_ip})...")
    start_t = time.time()
    confirmed_ip = None

    while time.time() - start_t < timeout_sec:
        try:
            data, addr = sock.recvfrom(2048)
            parsed = parse_dhcp_pkt(data)
            if not parsed:
                continue
            
            msg_type, xid, mac, mac_str = parsed
            if msg_type == 1: # DISCOVER
                print(f"[DHCP DISCOVER] From MAC {mac_str} (xid=0x{xid:08x}). Sending OFFER {assigned_ip}...")
                offer_pkt = make_dhcp_reply(2, xid, mac, assigned_ip, server_ip)
                sock.sendto(offer_pkt, ('255.255.255.255', 68))

            elif msg_type == 3: # REQUEST
                print(f"[DHCP REQUEST] From MAC {mac_str} (xid=0x{xid:08x}). Sending ACK {assigned_ip}...")
                ack_pkt = make_dhcp_reply(5, xid, mac, assigned_ip, server_ip)
                sock.sendto(ack_pkt, ('255.255.255.255', 68))
                print(f"🎉 [DHCP SUCCESS] Robot {mac_str} SUCCESSFULLY ASSIGNED IP: {assigned_ip}")
                confirmed_ip = assigned_ip
                break

        except socket.timeout:
            continue
        except Exception as e:
            print(f"[DHCP SERVER ERROR] {e}")
            break

    sock.close()
    return confirmed_ip

if __name__ == '__main__':
    run_dhcp_server()
