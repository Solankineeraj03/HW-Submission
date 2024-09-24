import socket
import ssl
import gzip
import logging

# Constants
BUFFER_SIZE = 4096
HTTP_VERSION = "HTTP/1.1"
TIMEOUT = 10  # Set a timeout for the socket connection

# Function to handle chunked transfer encoding
def handle_chunked_response(sock):
    body = b''
    while True:
        chunk_size_str = b''
        while b'\r\n' not in chunk_size_str:
            chunk_size_str += sock.recv(1)
        chunk_size = int(chunk_size_str.split(b'\r\n')[0], 16)
        if chunk_size == 0:
            sock.recv(2)  # Read final \r\n after the last chunk
            break
        chunk_data = b''
        while len(chunk_data) < chunk_size:
            chunk_data += sock.recv(min(BUFFER_SIZE, chunk_size - len(chunk_data)))
        body += chunk_data
        sock.recv(2)  # Consume the trailing \r\n after each chunk
    return body

# Helper function to extract the port from the URL
def get_host_and_port(url):
    if url.startswith("https://"):
        protocol = "https"
        default_port = 443
    elif url.startswith("http://"):
        protocol = "http"
        default_port = 80
    else:
        return None, None, None, None
    
    host_port = url.split("://")[1].split("/")[0]
    if ":" in host_port:
        host, port = host_port.split(":")
        port = int(port)
    else:
        host = host_port
        port = default_port
    
    path = "/" + "/".join(url.split("://")[1].split("/")[1:])
    return protocol, host, port, path

# Function to retrieve URL with proper handling of HTTP/1.1 features
def retrieve_url(url, max_redirects=5):
    sock = None
    try:
        protocol, host, port, path = get_host_and_port(url)
        if not protocol or not host or not path:
            logging.error(f"Invalid URL: {url}")
            return None

        # Create a socket and connect
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT)

        if protocol == "https":
            context = ssl.create_default_context()
            sock = context.wrap_socket(sock, server_hostname=host)

        sock.connect((host, port))

        # Send the HTTP GET request with User-Agent header
        request = f"GET {path} {HTTP_VERSION}\r\n" \
                  f"Host: {host}\r\n" \
                  f"Connection: close\r\n" \
                  f"User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36\r\n" \
                  f"\r\n"
        sock.sendall(request.encode())

        # Receive the response headers
        response = b""
        while b"\r\n\r\n" not in response:
            response += sock.recv(BUFFER_SIZE)

        headers, body = response.split(b"\r\n\r\n", 1)
        headers = headers.decode()

        # Check for redirection
        if "301" in headers or "302" in headers:
            for line in headers.splitlines():
                if "Location:" in line:
                    location = line.split("Location: ")[1].strip()
                    logging.info(f"Redirecting to {location}")
                    return retrieve_url(location, max_redirects - 1)

        # Check if the status code is 200
        if "200 OK" not in headers:
            logging.error(f"Non-200 status code: {headers.splitlines()[0]}")
            return None

        # Handle chunked transfer encoding
        if "Transfer-Encoding: chunked" in headers:
            body = handle_chunked_response(sock)

        # Handle gzip encoding if present
        if "Content-Encoding: gzip" in headers:
            body = gzip.decompress(body)

        # Handle content length for non-chunked responses
        if "Content-Length" in headers:
            content_length = None
            for line in headers.splitlines():
                if line.startswith("Content-Length:"):
                    content_length = int(line.split(":")[1].strip())
                    break
            if content_length is not None and len(body) < content_length:
                while len(body) < content_length:
                    body += sock.recv(min(BUFFER_SIZE, content_length - len(body)))

        return body

    except socket.timeout:
        logging.error("Socket timed out while waiting for response.")
    except ssl.SSLError as e:
        logging.error(f"SSL error occurred: {e}")
    except Exception as e:
        logging.error(f"Unexpected error occurred: {e}")
    finally:
        if sock:
            sock.close()
    return None

# Main execution block
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        sys.stdout.buffer.write(retrieve_url(sys.argv[1]))
    else:
        print("Usage: python hw1.py <url>")



