
import base64, sys
def write_file(path, b64):
    with open(path, 'wb') as f:
        f.write(base64.b64decode(b64))
    print(f'Written: {path}')

def write_text(path, b64):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(base64.b64decode(b64).decode('utf-8'))
    print(f'Written: {path}')
