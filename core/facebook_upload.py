"""Length-known multipart stream: do not load a long Final video into RAM."""
import os
import uuid


class VideoMultipart:
    def __init__(self, stream, fields):
        boundary = 'SmartFlow' + uuid.uuid4().hex
        chunks = []
        for name, value in fields.items():
            chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode('utf-8'))
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="source"; filename="final.mp4"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode())
        self.header = b''.join(chunks)
        self.footer = f'\r\n--{boundary}--\r\n'.encode()
        self.stream = stream
        self.size = os.fstat(stream.fileno()).st_size
        self.position = 0
        self.content_type = 'multipart/form-data; boundary=' + boundary

    def __len__(self):
        return len(self.header) + self.size + len(self.footer)

    def read(self, size=-1):
        remaining = len(self) - self.position
        size = remaining if size is None or size < 0 else min(size, remaining)
        parts = []
        while size > 0:
            if self.position < len(self.header):
                part = self.header[self.position:self.position + size]
            elif self.position < len(self.header) + self.size:
                part = self.stream.read(min(size, len(self.header) + self.size - self.position))
                if not part:
                    raise OSError('Video changed while uploading')
            else:
                offset = self.position - len(self.header) - self.size
                part = self.footer[offset:offset + size]
            parts.append(part)
            self.position += len(part)
            size -= len(part)
        return b''.join(parts)
