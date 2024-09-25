# Allowed Modules
import logging
import socket
import sys
import gzip
import ssl
# End of Allowed Modules

def retrieve_url(url):
    try:
        #checking if the url starts with https or http
        if url[:7] == "http://":
            scheme = "http"
            url = url[7:]
        elif url[:8] == "https://":
            scheme = "https"
            url = url[8:]
        else:
            raise ValueError("Invalid URL: Must start with 'http://' or 'https://'")

        #extracting the host and optional port
        path_start = url.find('/')
        if path_start != -1:
            host = url[:path_start]
            path = url[path_start:]
        else:
            host = url
            path = '/'  

        colon_pos = host.rfind(':')
        if colon_pos != -1:
            port_str = host[colon_pos + 1:]
            host = host[:colon_pos]
            try:
                port = int(port_str)
            except ValueError:
                logging.error(f"Invalid port number: {port_str}")
                return None
        else:
            # No port specified, use default based on scheme
            port = 443 if scheme == "https" else 80

        #for internationalized domain names (IDNA)
        try:
            host = host.encode('idna').decode('ascii')  # Handle non-ASCII characters in hostnames
        except UnicodeError:
            logging.error(f"Failed to encode hostname {host} using IDNA.")
            return None

        # making the first HTTP request
        response = get_http(host, path, port, scheme)
        if response is None:
            logging.debug(f"Request to {url} returned no response.")
            return None

        # making a second request
        second_response = get_http(host, path, port, scheme)
        if second_response is None:
            return None
        
        cleaned_response = clean_response(response)
        cleaned_second_response = clean_response(second_response)
        #if responses are different, then page is dynamic
        if cleaned_response != cleaned_second_response:
            logging.info("Dynamic content detected.")
            return None

        return response #first response
    except ValueError as e:
        logging.error(f"Value error occurred: {e}")
        return None
    except (socket.error, ssl.SSLError) as e:
        logging.error(f"Socket or SSL error occurred: {e}")
        return None
    except Exception as e:
        logging.error(f"Unhandled exception: {e}")
        return None


def get_http(host, path, port, scheme):
    try:
        #establishing a socket connection
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if scheme == "https":
            context = ssl.create_default_context()
            sock = context.wrap_socket(sock, server_hostname=host)

        logging.debug(f"Connecting to {host} on port {port}...")
        sock.connect((host, port))

        if (scheme == "http" and port != 80) or (scheme == "https" and port != 443):
            host_header = f"{host}:{port}"
        else:
            host_header = host

        #sending the HTTP GET request
        request = f"GET {path} HTTP/1.1\r\n"
        request += f"Host: {host_header}\r\n"  # Add port in Host header if non-standard
        request += "User-Agent: BarebonesHTTP/1.1\r\n"
        request += "Connection: close\r\n\r\n"
        logging.debug(f"Sending request: {request.strip()}")
        sock.sendall(request.encode())

        #receiving the HTTP response
        response = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk

        sock.close()

        headers, _, body = response.partition(b"\r\n\r\n")
        logging.debug(f"Received headers:\n{headers.decode(errors='replace')}")

        #to check for HTTP status code
        status_line = headers.split(b"\r\n")[0].decode()
        status_code = int(status_line.split()[1])

        #to handle non-200 status codes (e.g., 301, 302, 404)
        if status_code == 404:
            logging.error(f"404 Not Found: {status_line}")
            return None

        #to handle redirects (301, 302)
        if status_code in (301, 302):
            for line in headers.split(b"\r\n"):
                if line.startswith(b"Location:"):
                    new_url = line.split(b"Location:")[1].strip().decode()
                    if not new_url.startswith("http"):
                        new_url = f"{scheme}://{host}{new_url}"
                    logging.info(f"Redirecting to {new_url}")
                    return retrieve_url(new_url)

        if status_code != 200:
            logging.error(f"Received non-200 status code: {status_code}")
            return None

        #trying to handle chunked encoding and gzip, if needed
        if b"Transfer-Encoding: chunked" in headers:
            body = process_chunked_body(body)

        if b"Content-Encoding: gzip" in headers:
            body = gzip.decompress(body)

        return body
    except Exception as e:
        logging.error(f"Socket connection failed: {e}")
        return None


def process_chunked_body(data):#used for processing chunk transfer encoding and to return the whole html body
    full_body = b""
    idx = 0

    while idx < len(data):
        # Locate the end of the chunk size line
        end_of_size = data.find(b"\r\n", idx)
        if end_of_size == -1:
            logging.error("Error: Missing chunk size CRLF.")
            return full_body

        #extracting the chunk size
        chunk_size_str = data[idx:end_of_size].strip()
        try:
            chunk_size = int(chunk_size_str, 16)
        except ValueError:
            logging.error("Error: Invalid chunk size.")
            return full_body

        if chunk_size == 0:
            break  #end of chunks
        idx = end_of_size + 2  # Skip the CRLF after the size

        chunk_data = data[idx:idx + chunk_size] #adding the current chunk to the whole body
        full_body += chunk_data

        idx += chunk_size + 2

    return full_body



def clean_response(response):#used for cleaning the response by removing dynamic elements
    cleaned_response = response.replace(b"session_id=", b"").replace(b"timestamp=", b"")#removing timestamps and session ids
    return cleaned_response



