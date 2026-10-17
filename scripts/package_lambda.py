"""Build the API Gateway Lambda for Python 3.13 x86_64 without the offline UI dependencies."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
root=Path(__file__).resolve().parents[1]
(root/'dist').mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as staging:
    subprocess.run([sys.executable,'-m','pip','install','-r',str(root/'requirements-lambda.lock'),
        '--target',staging,'--platform','manylinux2014_x86_64','--implementation','cp',
        '--python-version','3.13','--abi','cp313','--only-binary=:all:','--no-compile'],check=True)
    target=Path(staging)/'app';target.mkdir()
    for name in ['__init__.py','aws_backend.py','schemas.py','lambda_handler.py']:
        shutil.copyfile(root/'app'/name,target/name)
    shutil.make_archive(str(root/'dist'/'lambda'),'zip',staging)
print('Built dist/lambda.zip for Lambda Python 3.13 x86_64')
