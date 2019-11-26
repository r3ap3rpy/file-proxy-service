import os
import json
import zlib
import zipfile
import base64
import paramiko
import winrm
from datetime import datetime
from flask import Flask
from flask_apscheduler import APScheduler
from dotenv import load_dotenv

load_dotenv('.env')

RunningConfig = {}

RemoteDestination = False
ConfigItems = ['IN','OUT','REMOTESERVER','REMOTEUSER','REMOTEPASS','SMTPSERVER','SMTPRECIPIENTS','SMTPSENDER']

for item in ConfigItems:
    RunningConfig[item] = ('N.A.' if not os.getenv(item) else os.getenv(item))
    if os.getenv(item):
        print(f"Initial config: {item} = {os.getenv(item)}")
    else:
        if item in ['IN','OUT']:
            raise SystemExit("Mandatory config item is missing: {item}, cannot continue!")
        else:
            print(f"This is an optional configuration item: {item}")

if not os.path.isdir(os.getenv('IN')):
    raise SystemExit('The input folder must be an absolute path, aborting!')
else:
    print(f"Using the following input folder: {os.getenv('IN')}")

if not os.path.isdir(os.getenv('OUT')):
    if os.getenv('REMOTESERVER') and os.getenv('REMOTEUSER') and os.getenv('REMOTEPASS'):
        print(f"Using the following remote output folder: {os.getenv('REMOTESERVER')}::{os.getenv('OUT')}")
        RemoteDestination = True
    else:
        raise SystemExit('The output folder must be an absolute path because you have NOT specified a remote address, aborting!')
else:
    if os.getenv('REMOTESERVER') and os.getenv('REMOTEUSER') and os.getenv('REMOTEPASS'):
        print(f"Using the following remote output folder: {os.getenv('REMOTESERVER')}::{os.getenv('OUT')}")
        RemoteDestination = True
    else:
        print(f"Using the following output folder: {os.getenv('OUT')}")

RemoteCopy = ''
if os.getenv('REMOTESERVER') and os.getenv('REMOTEUSER') and os.getenv('REMOTEPASS'):
    RemoteDestination = True
    print(f"Verifying ssh authentication and remote path: {os.getenv('OUT')} on system: {os.getenv('REMOTESERVER')}")
    try:
        #ssh = paramiko.SSHClient() 
        #ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy()) 
        #ssh.connect(os.getenv('REMOTESERVER'), username=os.getenv('REMOTEUSER'), password=os.getenv('REMOTEPASS'))      
        #dircheck = """ 
        #if [ -d "%s" ]; then          
        #  echo "True"
        #else
        #  echo "False"
        #fi
        #"""  % (os.getenv('OUT'))        
        #stdin, stdout, stderr = ssh.exec_command(dircheck)
        #output = stdout.readlines()
        #ssh.close()
        #if len(output) == 0:
        #    raise SystemExit("Unknown error!")
        #elif output[0].replace('\n','') == 'True':
        #    print("Good to go, remote path exists, and credentials are working!")
        #    RemoteCopy = 'ssh'
        #else:
        #    raise SystemExit("The remote path does not exists on the system...")
        ...
    except Exception as e:
        print(f"SSH connection failed, trying winrm for windows because: {e}")
        if '@' in os.getenv('REMOTEUSER'):
            print(f"Verifying ntlm authentication and remote path: {os.getenv('OUT')} on system: {os.getenv('REMOTESERVER')}")
            try:
                prot = winrm.protocol.Protocol(
                        endpoint = f"http://{os.getenv('REMOTESERVER')}:5985/wsman",
                        transport = "ntlm",
                        username = os.getenv('REMOTEUSER'),
                        password = os.getenv('REMOTEPASS'),
                        server_cert_validation = "ignore"
                )
                shell = prot.open_shell()
                command = prot.run_command(shell, f"powershell -c Test-Path -Path {os.getenv('OUT')}")
                out, err, status = prot.get_command_output(shell, command)
                prot.cleanup_command(shell, command)
                prot.close_shell(shell)
                print(out)
                if out.decode().replace('\r\n','') == 'True':
                    print("Good to go, remote path exists, and credentials are working!")
                    RemoteCopy = 'ntlm'
                else:
                    raise SystemExit("The remote path does not exists on the system...")
            except Exception as e:
                raise SystemExit(f"Cannot verify remote path for Basic authentication because: {e}")
        else:
            print(f"Verifying basic authentication and remote path: {os.getenv('OUT')} on system: {os.getenv('REMOTESERVER')}")
            try:
                Session = winrm.Session(os.getenv('REMOTESERVER'), auth = (os.getenv('REMOTEUSER'), os.getenv('REMOTEPASS')))
                Response = Session.run_ps(f"Test-Path -Path {os.getenv('OUT')}")
                if Response.std_out.decode().replace('\r\n','') == 'True':
                    print("Good to go, remote path exists, and credentials are working.")
                    RemoteCopy = 'basic'
                else:
                    raise SystemExit("The remote path does not exists on the system...")
            except Exception as e:
                raise SystemExit(f"Cannot verify remote path for Basic authentication because: {e}")



app = Flask(__name__)
scheduler = APScheduler()
RunningStats = {}
statid = 1
def copyproxy():
    if len(os.listdir(os.getenv('IN'))) > 0:
        for file in os.listdir(os.getenv('IN')):
            gzipFile = (file.split('/')[-1].split('.')[0] + '.zip')
            inputFile = os.path.sep.join([os.getenv('IN'),file])
            print(f"Compressing file: {inputFile}")

            with zipfile.ZipFile(gzipFile, mode = 'w', compression = zipfile.ZIP_DEFLATED) as myzip:
                myzip.write(inputFile,file)
                try: 
                    compress_ratio = 'Compressed: %d%%' % (100.0 *  ((float(os.stat(inputFile).st_size) - float(os.stat(gzipFile).st_size) / float(os.stat(inputFile).st_size))))
                    print(compress_ratio)
                except ZeroDivisionError as e:
                    print(f"Empty files cennot be compressed, because:{e} skipping...")
                    continue                                

            if RemoteDestination:
                print(f"Pushing file to remote server: {os.getenv('REMOTESERVER')}")
                #gzipFile = (file.split('/')[-1].split('.')[0] + '.gzip')
                #with open(gzipFile,'wb') as result:
                #    result.write(compressed)                
                def chunker(seq, size):
                    return (seq[pos:pos + size] for pos in range(0, len(seq), size))
                if RemoteCopy == 'ssh':
                    ssh = paramiko.SSHClient() 
                    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy()) 
                    ssh.connect(os.getenv('REMOTESERVER'), username=os.getenv('REMOTEUSER'), password=os.getenv('REMOTEPASS'))
                    sftp = ssh.open_sftp()
                    sftp.put(os.path.sep.join([os.path.abspath('.'),gzipFile]), (os.getenv('OUT') + ('\\' if '\\' in os.getenv('OUT') else '/') + gzipFile))
                    sftp.close()
                    ssh.close()
                elif RemoteCopy == 'basic':                    
                    Session = winrm.Session(os.getenv('REMOTESERVER'), auth = (os.getenv('REMOTEUSER'), os.getenv('REMOTEPASS')))
                    with open(gzipFile, 'rb') as binaryFile:
                        data = base64.b64encode(binaryFile.read())
                    for chunk in chunker(data,512):   
                        chunk = chunk.decode()                                             
                        Response = Session.run_ps(f"'{chunk}' | Out-File -FilePath '{os.getenv('OUT')}\\{gzipFile}.tmp' -Append -NoNewLine")                        
                        
                    Response = Session.run_ps(f"[System.Convert]::FromBase64String((Get-Content '{os.getenv('OUT')}\\{gzipFile}.tmp'))| set-content '{os.getenv('OUT')}\\{gzipFile}' -encoding byte;Remove-Item -Path '{os.getenv('OUT')}\\{gzipFile}.tmp' -Force")

                else:
                    prot = winrm.protocol.Protocol(
                            endpoint = f"http://{os.getenv('REMOTESERVER')}:5985/wsman",
                            transport = "ntlm",
                            username = os.getenv('REMOTEUSER'),
                            password = os.getenv('REMOTEPASS'),
                            server_cert_validation = "ignore"
                    )
                    shell = prot.open_shell()
                    with open(gzipFile, 'rb') as binaryFile:
                        data = base64.b64encode(binaryFile.read())

                    for chunk in chunker(data,512):   
                        chunk = chunk.decode()                        

                        command = prot.run_command(shell, f"""powershell -c "'{chunk}' | Out-File -FilePath '{os.getenv('OUT')}\\{gzipFile}.tmp' -Append -NoNewLine" """)
                        out, err, status = prot.get_command_output(shell, command)
                    
                    command = prot.run_command(shell, f"""powershell -c "[System.Convert]::FromBase64String((Get-Content '{os.getenv('OUT')}\\{gzipFile}.tmp'))| set-content '{os.getenv('OUT')}\\{gzipFile}' -encoding byte;Remove-Item -Path '{os.getenv('OUT')}\\{gzipFile}.tmp' -Force" """)
                    out, err, status = prot.get_command_output(shell, command)
                    prot.cleanup_command(shell, command)
                    prot.close_shell(shell)
                os.remove(gzipFile)
                os.remove(inputFile)
                RunningStats[str(datetime.now())] = {'IN':inputFile,'OUT':(os.getenv('REMOTESERVER') + "::" + (os.getenv('OUT')+(os.getenv('OUT') + ('\\' if '\\' in os.getenv('OUT') else '/') + gzipFile))),'Ratio':compress_ratio}
            else:
                print(f"Pushing device to output location: {os.path.sep.join([os.getenv('OUT'),(file.split('.')[0] + '.gzip')])}")
                outputFile = os.path.sep.join([os.getenv('OUT'),(file.split('/')[-1].split('/')[-1].split('.')[0] + '.gzip')])
                with open(outputFile,'wb') as result:
                    result.write(compressed)
                os.remove(inputFile)
                RunningStats[str(datetime.now())] = {'IN':inputFile,'OUT':(os.getenv('OUT')+(os.getenv('OUT') + ('\\' if '\\' in os.getenv('OUT') else '/') + gzipFile)),'Date':str(datetime.now()),'Ratio':compress_ratio}
    
    else:
        print("Dryrun, nothing to do!")
    

@app.route('/')
def index():
    return """<H1>Welcome to the app</H1>
                <br>
                <a href="/config">Runninh Configuration</a> 
                <br>
                <a href="/stats">Statistics</a> 
    """

@app.route('/config')
def config():
    return RunningConfig

@app.route('/stats')
def statistics():
    return RunningStats

if __name__ == '__main__':
    scheduler.add_job(id="Zipper", func=copyproxy, trigger='interval', seconds=3)
    scheduler.start()
    app.run(host = '0.0.0.0', port = 8080)
