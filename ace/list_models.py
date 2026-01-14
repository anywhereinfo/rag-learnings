import subprocess
import json

try:
    token = subprocess.check_output(['gcloud', 'auth', 'print-access-token']).decode().strip()
    cmd = [
        'curl', '-s', '-X', 'GET',
        '-H', f'Authorization: Bearer {token}',
        'https://us-central1-aiplatform.googleapis.com/v1/projects/gcp-prj-ntpc-np-01/locations/us-central1/publishers/google/models'
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    data = json.loads(result.stdout)
    if 'models' in data:
        print(f"Found {len(data['models'])} models.")
        for m in data['models']:
            name = m.get('name', '').split('/')[-1]
            if 'gemini' in name.lower() or 'bison' in name.lower():
                print(f"- {name}")
    else:
        print("No models found or API error:")
        print(result.stdout[:500])
        
except Exception as e:
    print(f"Error: {e}")
    if 'result' in locals():
        print("Raw Output:")
        print(result.stdout)
        print("Raw Error:")
        print(result.stderr)
