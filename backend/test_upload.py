import requests
import time
import json

def run_test():
    print('=== UPLOADING ===')
    try:
        with open('dummy_with_audio.mp4', 'rb') as f:
            res = requests.post('http://127.0.0.1:8000/api/v1/recordings/upload', files={'file': ('test.mp4', f, 'video/mp4')})
        
        data = res.json()
        print(json.dumps(data, indent=2))
        rec_id = data.get('recording_id')
        
        if not rec_id:
            print("Failed to get recording ID")
            return
            
        print('\n=== POLLING STATUS ===')
        for i in range(24):
            time.sleep(5)
            try:
                s = requests.get(f'http://127.0.0.1:8000/api/v1/recordings/{rec_id}/status').json()
                msg = s.get("progress_message", "")
                try:
                    print(f'[{(i+1)*5}s] status={s.get("status")} | {msg}')
                except UnicodeEncodeError:
                    print(f'[{(i+1)*5}s] status={s.get("status")} | {msg.encode("ascii", "ignore").decode("ascii")}')
                
                if s.get('status') in ('ANALYZED', 'FAILED', 'COMPLETED'):
                    if s.get('error_message'):
                        print('ERROR:', s['error_message'])
                    break
            except Exception as e:
                print(f"Error polling: {e}")
                
    except Exception as e:
        print(f"Upload failed: {e}")

if __name__ == '__main__':
    run_test()
