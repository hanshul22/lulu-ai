import subprocess
import time
import sys
import os

def run_application():
    """
    Runs the main application (run.py) and restarts it if it crashes.
    """
    script_path = os.path.join(os.path.dirname(__file__), "run.py")
    
    print("🚀 Starting Auto-Restart Service for LULU AI...")
    print(f"📂 Target Script: {script_path}")
    print("---------------------------------------------------")

    while True:
        try:
            print(f"\n[🔄] Launching application at {time.strftime('%Y-%m-%d %H:%M:%S')}...")
            
            # Run the process
            process = subprocess.Popen([sys.executable, script_path])
            
            # Wait for the process to complete
            return_code = process.wait()
            
            if return_code == 0:
                print("[✅] Application exited normally. Stopping service.")
                break
            else:
                print(f"[⚠️] Application crashed with exit code {return_code}.")
                print("[⏳] Restarting in 3 seconds...")
                time.sleep(3)
                
        except KeyboardInterrupt:
            print("\n[🛑] Auto-Restart Service stopped by user.")
            break
        except Exception as e:
            print(f"\n[❌] Critical Error in Auto-Restart Service: {e}")
            time.sleep(5)

if __name__ == "__main__":
    run_application()
