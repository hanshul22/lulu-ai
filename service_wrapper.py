import sys
import os
import win32serviceutil
import win32service
import win32event
import servicemanager
import logging
import logging.handlers

# Ensure src is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

try:
    from main import run_app as worker_run
except ImportError:
    # Fallback for when running as exe where src might be bundled differently
    # or if run from a different CWD
    sys.path.append(os.path.abspath(os.path.dirname(__file__)))
    from src.main import run_app as worker_run

class MyPythonBackgroundService(win32serviceutil.ServiceFramework):
    _svc_name_ = "LuluAIHelper"
    _svc_display_name_ = "Lulu AI Helper Service"
    _svc_description_ = "Runs the Lulu AI Automation Assistant as a background service."

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.running = True
        self.setup_logging()

    def setup_logging(self):
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "service.log")
        
        handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=5*1024*1024, backupCount=5
        )
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        
        self.logger = logging.getLogger("LuluService")
        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(handler)

    def SvcStop(self):
        self.logger.info("Service stop signal received.")
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.running = False
        win32event.SetEvent(self.hWaitStop)
        # In a real GUI app like this, we might need to forcefully kill the process 
        # or signal the main thread to exit if it's blocking on a GUI loop.
        # Since run_app blocks on Tkinter mainloop, we might need to rely on OS process termination
        # or implement a more complex signaling mechanism. 
        # For now, setting the event is standard.

    def SvcDoRun(self):
        self.logger.info("Service starting...")
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
        )
        self.main()

    def main(self):
        try:
            self.logger.info("Calling worker_run()...")
            worker_run()
        except Exception as e:
            self.logger.error(f"Exception in worker_run: {e}", exc_info=True)
            servicemanager.LogErrorMsg(f"Service error: {e}")

if __name__ == "__main__":
    if len(sys.argv) == 1:
        print(
            "Usage:\n"
            "  service_wrapper.exe install   -> Install service\n"
            "  service_wrapper.exe start     -> Start service\n"
            "  service_wrapper.exe stop      -> Stop service\n"
            "  service_wrapper.exe remove    -> Uninstall service\n"
        )
        # Also allow running as a script for testing
        # win32serviceutil.HandleCommandLine(MyPythonBackgroundService)
    else:
        win32serviceutil.HandleCommandLine(MyPythonBackgroundService)
