# ==================================================
# !/usr/bin/env python
# @Author: simon.zhang
# @Date: 2025/8/05 14:21
# @FileName: ble_control.py
# @Email: wangfu_zhang@ggec.com.cn
# Function: Connect to BLE via the hcitool command
# ==================================================

# Import dependent modules with comments on their core functions
import os
import re
import time
import subprocess
import sys
import select
import fcntl
from collections import Counter  # For counting statistics

# Add path for importing LPS_modules
currdir = os.getcwd()
projdir = currdir.split("/Python")
lpsmoduledir = projdir[0] + "/Python/Test_Cases/Low_Power_Sequence"
sys.path.append(lpsmoduledir)

# Import logging function from LPS_modules
try:
    from LPS_modules import thread_terminal_logging
except ImportError:
    # Fallback function if import fails (for standalone usage)
    def thread_terminal_logging(uut_name, level, message):
        print(f"[{uut_name}] {level.upper()}: {message}")


class BLEConnector:
    """Encapsulates BLE connection functionality for device wake-up in reliability testing"""

    def __init__(self, ble_mac_address, max_retries=3):
        """
        Initialize BLE connector
        :param ble_mac_address: Target BLE device MAC address
        :param max_retries: Maximum number of retries (default 3, for retry after failed operations like scanning, connecting)
        """
        # Validation for an empty device MAC address
        if not ble_mac_address or not isinstance(ble_mac_address, str) or ble_mac_address.strip() == "":
            raise ValueError(f"BLE device MAC address cannot be empty, Received: {ble_mac_address}")
        # Initialize core parameters
        self.ble_mac_address = ble_mac_address  # Target BLE device MAC address
        self.max_retries = max_retries  # Default maximum retry count for all retryable operations

        # Automatically detect USB Bluetooth adapter in the system (exclude virtual devices to ensure hardware validity)
        self.hci_device = self._detect_usb_bluetooth_dongle()
        thread_terminal_logging("uut", "info", f"Using Bluetooth adapter:{self.hci_device}")

        # Connection process state tracking variables
        self.connection_success = False
        self.lock_file = None
        self.lock_fd = None  # Used to store the file descriptor

        # Ensure Bluetooth adapter is available during initialization, exit if unavailable
        if not self.ensure_adapter_ready():
            thread_terminal_logging("UUT", "error", f"Bluetooth adapter unavailable, exiting program")
            sys.exit(1)

    def _detect_usb_bluetooth_dongle(self):
        """Detect USB Bluetooth adapters in the system (exclude virtual devices),
         returns first available USB Bluetooth device name (e.g., hci0)"""
        try:
            # Execute hciconfig command to get all Bluetooth device information (hciconfig is Linux Bluetooth tool)
            result = subprocess.run(
                ['hciconfig'],
                capture_output=True,
                text=True,
                timeout=10
            )
            # Check command execution result: non-zero return code indicates failure (e.g., hciconfig not installed)
            if result.returncode != 0:
                thread_terminal_logging("uut", "error", f"Failed to retrieve Bluetooth device information")
                sys.exit(1)

            # Parse hciconfig output to extract USB Bluetooth devices
            output = result.stdout
            lines = output.split('\n')

            usb_devices = []
            current_device = None

            for line in lines:
                # 1. Check if line represents a Bluetooth device: format "hciX:" (X is number, e.g., hci0:)
                if ':' in line and line.strip().startswith('hci'):
                    parts = line.split(':')  # Split "hci0:" into ["hci0", ""]
                    current_device = parts[0].strip()  # Extract device name (e.g., hci0)

                    # Check if device is USB type (exclude virtual devices, USB devices have "Bus: USB" identifier)
                    if 'Bus: USB' in line:
                        usb_devices.append(current_device)  # Add to USB device list
                        thread_terminal_logging("uut", "info", f"Found USB Bluetooth device: {current_device}")

                # 2. Check if current device is active (UP RUNNING)
                elif current_device and 'UP RUNNING' in line:
                    # If active device is in USB device list, prefer this device (plug-and-play and already active)
                    if current_device in usb_devices:
                        thread_terminal_logging("UUT", "info", f"Selecting UP state USB device: {current_device}")
                        return current_device  # Return active USB device directly, no need to continue searching

            # If no active USB device found but USB devices exist, select first USB device
            if usb_devices:
                selected = usb_devices[0]
                thread_terminal_logging("uut", "info", f"Selecting USB Bluetooth device: {selected}")
                return selected

            # No USB Bluetooth devices found (may not be inserted or driver not recognized)
            thread_terminal_logging("uut", "error", f"No USB Bluetooth dongle found")
            sys.exit(1)

        except Exception as e:
            thread_terminal_logging("uut", "error", f"Error detecting USB Bluetooth dongle: {e}")
            sys.exit(1)

    def _run_command(self, cmd, timeout=30):
        """
        Universal system command execution function: supports timeout control, real-time logging, returns command execution results
        :param cmd: System command to execute (string format, e.g., "hciconfig hci0 up")
        :param timeout: Command execution timeout in seconds (default 30)
        :return: stdout (command standard output), stderr (command error output), return_code (return code), timed_out (whether timeout occurred)
        """
        thread_terminal_logging("uut", "debug", f"Executing command :{cmd}")

        try:
            # Create subprocess to execute command: shell=True allows complex commands (e.g., pipes, redirects)
            process = subprocess.Popen(
                cmd,
                shell=True,  # Allow execution of commands containing complex syntax such as pipelines and redirects
                stdout=subprocess.PIPE,  # Redirect standard output to pipe
                stderr=subprocess.PIPE,  # Redirect error output to pipe
                text=True
            )

            # Initialize output storage dictionary: stores stdout and stderr contents separately
            outputs = {"stdout": [], "stderr": []}
            fds = [process.stdout, process.stderr]  # File descriptors to monitor (stdout and stderr)

            start_time = time.time()
            timed_out = False

            # Loop to monitor file descriptors until all streams close or timeout
            while fds and not timed_out:
                # Calculate remaining timeout time (prevent cumulative error)
                time_remaining = timeout - (time.time() - start_time)
                if time_remaining <= 0:  # remaining time <=0 ,judged as timeout
                    timed_out = True #Timeout marker
                    break

                # Use select to monitor file descriptors: wait for readable events with remaining time as timeout
                ready, _, _ = select.select(fds, [], [], time_remaining)
                if not ready:
                    continue  #No output, continue waiting

                # Process readable file descriptors (stdout or stderr)
                for fd in ready:
                    try:
                        line = fd.readline().strip()  # Read one line and remove leading/trailing whitespace
                        if line:  # If content was read (non-empty line)
                            if fd == process.stdout:  # Distinguish between stdout and stderr
                                thread_terminal_logging("uut", "debug", f"STDOUT: {line}")
                                outputs["stdout"].append(line)
                            else:
                                thread_terminal_logging("uut", "debug", f"STDERR: {line}")
                                outputs["stderr"].append(line)
                        else:  # Empty line indicates stream closed (EOF), remove from monitoring list
                            fds.remove(fd)
                    except Exception as e:
                        thread_terminal_logging("uut", "warning", f"Error reading output")
                        if fd in fds:
                            fds.remove(fd)

            # Handle command timeout: terminate subprocess and clean up resources
            if timed_out:
                process.terminate()  # First try graceful termination
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                thread_terminal_logging("uut", "error", f"Command timed out: {cmd}")
                return "", "Command execution timed out", -1, True

            # Command completed normally, get process return code
            return_code = process.wait()

            # Combine output lists into strings (join lines with newlines)
            stdout = "\n".join(outputs["stdout"])
            stderr = "\n".join(outputs["stderr"])

            thread_terminal_logging("uut", "debug", f"Command return code: {return_code}")
            return stdout, stderr, return_code, False  # Return normal execution results

        except Exception as e:
            # Catch exceptions during command execution (e.g., failed to create subprocess)
            thread_terminal_logging("uut", "error", f"Command execution : {e}")
            return f"Exception: {e}", "Execution error", -1, False

    def _retry_operation(self, operation_func, operation_name, *args, **kwargs):
        """
        Universal retry operation function: provides "failure retry + exponential backoff waiting" logic for any operation
        Exponential backoff: retry interval grows as 2^n with each attempt (maximum 30 seconds), avoiding frequent retries consuming resources
        :param operation_func: Target function to execute (e.g., scanning, connecting, resetting adapter)
        :param operation_name: Operation name (for logging, e.g., "scan device")
        :param *args: Positional arguments passed to target function (e.g., no additional arguments for scanning)
        :param *kwargs: Keyword arguments passed to target function, supports max_retries to override default retry count
        :return: Return value of target function when successful; None if all retries fail
        """
        # Prefer max_retries from kwargs, use class initialization default if not provided
        max_retries = kwargs.pop('max_retries', self.max_retries)

        # Loop to perform retries: from 1 to max_retries attempts
        for attempt in range(1, max_retries + 1):
            try:
                thread_terminal_logging("uut", "info", f"Performing {operation_name}(attempt {attempt}/{max_retries})")

                # Call target function with positional and keyword arguments
                result = operation_func(*args, **kwargs)

                # Determine if operation succeeded: result is considered successful if not False or None (different operations have different return values)
                if result is not False and result is not None:
                    return result  # Success, return result

                # Operation failed and not reached maximum retries, calculate wait time and retry
                if attempt < max_retries:
                    wait_time = min(2 ** attempt, 30)  # Exponential backoff: 2^attempt seconds, maximum 30 seconds
                    thread_terminal_logging("uut", "info", f"waiting {wait_time} Seconds before retry")
                    time.sleep(wait_time)

            except Exception as e:
                # Catch exceptions during target function execution (e.g., file read errors during scanning)
                thread_terminal_logging("uut", "error", f"Error performing {operation_name}: {e}")
                # Wait and retry if not reached maximum retries
                if attempt < max_retries:
                    wait_time = min(2 ** attempt, 30)
                    thread_terminal_logging("uut", "info", f"waiting {wait_time} seconds before retry")
                    time.sleep(wait_time)

        # All retry attempts exhausted with failure
        thread_terminal_logging("uut", "error", f"Error:Exceeded maximum retry count {max_retries}")
        return None  # All retries hava failed,and the upper layer will handle it accordingly(such as terminating the process)

    def reset_adapter(self):
        """Reset Bluetooth adapter: down->reset->up, restore adapter to initial state (resolve some connection anomalies)"""

        # Internal implementation function: encapsulates reset logic (passed to _retry_operation for retries)
        def _reset_impl():
            try:
                # 1. Turn off Bluetooth adapter (down command)
                self._run_command(f"sudo hciconfig {self.hci_device} down")
                time.sleep(1)

                # 2. Perform adapter reset (reset command)
                self._run_command(f"sudo hciconfig {self.hci_device} reset")
                time.sleep(2) # wait for 2s to allow time for hardware reset

                # 3. Re-enable adapter (up command)
                self._run_command(f"sudo hciconfig {self.hci_device} up")
                time.sleep(2) # wait for 2s to ensure activation is complete

                # 4. Check if adapter is in UP RUNNING state after reset (verify reset success)
                stdout, _, _, _ = self._run_command(f"hciconfig {self.hci_device}")

                if "UP RUNNING" in stdout:
                    thread_terminal_logging("uut", "info", f"Adapter {self.hci_device} reset successful")
                    return True  # single reset successful
                else:
                    thread_terminal_logging("uut", "warning", f"Adapter state abnormal: {stdout}")
                    return False # exception occurred,reset failed

            except Exception as e:
                thread_terminal_logging("uut", "error", f"Error resetting adapter: {e}")
                return False

        # Call universal retry function to perform reset operation (retry logic handled by _retry_operation)
        return self._retry_operation(_reset_impl, "reset adapter")

    def ensure_adapter_ready(self):
        """Ensure Bluetooth adapter is in usable state (UP RUNNING): attempt activation if not active"""

        # Internal implementation function: encapsulates adapter state check and activation logic
        def _ensure_impl():
            try:
                # 1. First check current adapter state
                stdout, _, _, _ = self._run_command(f"hciconfig {self.hci_device}")

                # Return success if already in UP RUNNING state
                if "UP RUNNING" in stdout:
                    thread_terminal_logging("uut", "info", f"Adapter {self.hci_device} is already enabled")
                    return True

                # 2. Adapter not active, attempt activation with up command
                thread_terminal_logging("uut", "warning", f"Adapter {self.hci_device} not enabled, attempting activation...")
                self._run_command(f"sudo hciconfig {self.hci_device} up")
                time.sleep(2)  # wait for 2 seconds to ensure activation is complete

                # 3. Check state again after activation
                stdout, _, _, _ = self._run_command(f"hciconfig {self.hci_device}")
                if "UP RUNNING" in stdout:
                    thread_terminal_logging("uut", "info", f"Adapter {self.hci_device} activation successful")
                    return True # activation successful
                else:
                    thread_terminal_logging("uut", "warning", f"Adapter state after activation:{stdout}")
                    return False  # abnormal Status after activation，failed

            except Exception as e:
                thread_terminal_logging("uut", "error", f"Error checking adapter state: {e}")
                return False

        # Call universal retry function to ensure adapter readiness (retry on activation failure)
        return self._retry_operation(_ensure_impl, "ensure adapter ready")


    def acquire_lock(self, max_retries=3):
        """Acquire lock file (uses fcntl to implement reliable inter-process file locking)"""

        def _acquire_lock_impl():
            lock_file = f"/tmp/.ble_lock_{self.hci_device}"
            max_wait = 30  # Maximum waiting time in seconds

            try:
                # Open or create the lock file
                # os.O_CREAT: Create file if it doesn't exist; os.O_RDWR: Read-write mode; 0o644: File permission (owner r/w, others r)
                fd = os.open(lock_file, os.O_CREAT | os.O_RDWR, 0o644)

                # Attempt to acquire a non-blocking exclusive lock
                try:
                    # fcntl.LOCK_EX: Exclusive lock (only one process can hold it at a time)
                    # fcntl.LOCK_NB: Non-blocking mode (raise error immediately if lock is held)
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    # Lock acquired successfully, write PID to the file
                    os.ftruncate(fd, 0)  # Clear the file content (remove historical PID)
                    os.write(fd, str(os.getpid()).encode())  # Write current process PID for debugging
                    thread_terminal_logging("uut", "info", f"Created lock file: {lock_file}")
                    self.lock_fd = fd  # Save file descriptor for subsequent release
                    return lock_file

                except BlockingIOError:
                    # Lock is held by another process, enter waiting logic
                    thread_terminal_logging("uut", "info", f"Lock is held by another process,waiting...")

                    start_time = time.time()
                    # Retry every 0.1 seconds until timeout (balances response speed and CPU usage)
                    while time.time() - start_time < max_wait:
                        try:
                            # Retry acquiring the non-blocking exclusive lock
                            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                            os.ftruncate(fd, 0)  # Clear file content
                            os.write(fd, str(os.getpid()).encode())  # Write current process PID
                            thread_terminal_logging("uut", "info", f"Created lock file: {lock_file}")
                            self.lock_fd = fd
                            return lock_file

                        except BlockingIOError:
                            time.sleep(0.1)  # Short delay to reduce CPU consumption

                    # Timeout occurred, clean up resources
                    os.close(fd)  # Close file descriptor to avoid leakage
                    thread_terminal_logging("uut",
                                            "warning",
                                            f"Lock waiting timed out ({max_wait}s, proceeding forcefully")
                    return None

            except Exception as e:
                thread_terminal_logging("uut", "error", f"Failed to acquire lock")
                return None

        # Call the universal retry function (retry on acquisition failure)
        return self._retry_operation(_acquire_lock_impl, "acquire lock", max_retries=max_retries)


    def release_lock(self):
        """Release the lock file (with error handling)"""
        # Release the fcntl lock first (kernel-level lock release)
        if hasattr(self, 'lock_fd') and self.lock_fd is not None:
            try:
                fcntl.flock(self.lock_fd, fcntl.LOCK_UN)  # LOCK_UN: Release the held lock
                os.close(self.lock_fd)  # Close file descriptor to free system resources
                self.lock_fd = None  # Reset to indicate no active lock
                thread_terminal_logging("uut", "info", f"Successfully released fcntl lock")
            except Exception as e:
                thread_terminal_logging("uut", "error", f"Failed to release fcntl lock: {e}")

        # Delete the lock file (retain original cleanup logic)
        if self.lock_file and os.path.exists(self.lock_file):
            try:
                os.remove(self.lock_file)  # Delete the lock file to avoid residual files
                thread_terminal_logging("uut", "info", f"Released lock file: {self.lock_file}")
                self.lock_file = None  # Reset to indicate no lock file exists
            except Exception as e:
                thread_terminal_logging("uut", "error", f"Failed to release lock file: {e}")
        else:
            thread_terminal_logging("uut", "info", f"No lock file to release")

    def connect_device(self, ble_mac_address):
        """Perform BLE device connection: use hcitool lecc command to connect to target device (requires MAC address)"""

        # Internal implementation function: encapsulates connection logic
        def _connect_impl():
            # First check if MAC address is valid (avoid connection failure due to invalid parameters)
            if not ble_mac_address:
                thread_terminal_logging("uut", "error", f"Invalid Mac address, skipping connection")
                return False

            try:
                # 1. Stop all Bluetooth-related processes (clean up previous connection leftovers)
                thread_terminal_logging("uut", "info", f"Stopping all Bluetooth-related processes")
                self._run_command("sudo pkill -f hcitool", timeout=5)
                time.sleep(2)

                # 2. Reset adapter (restore initial state, resolve connection leftover issues)
                thread_terminal_logging("uut", "info", f"Resetting Bluetooth adapter state")
                self._run_command(f"sudo hciconfig {self.hci_device} reset", timeout=10)
                time.sleep(2)

                # 3. Execute BLE connection command: lecc (LE Connection Command)
                thread_terminal_logging("uut", "info", f"Connecting to device {ble_mac_address} using hcitool")
                cmd = f"sudo timeout 30 hcitool -i {self.hci_device} lecc --random {ble_mac_address}"
                # Execute command with timeout set to 35 seconds (5 seconds more than internal command timeout to avoid false timeout judgment)
                stdout, stderr, return_code, timed_out = self._run_command(cmd, timeout=35)

                # 4. Record detailed connection command results (for debugging)
                thread_terminal_logging(
                    "uut",
                    "debug",
                     f"Connection command results: time_out={timed_out}, return_code={return_code}")
                thread_terminal_logging("uut", "debug", f"STDOUT: {stdout}")
                thread_terminal_logging("uut", "debug", f"STDERR: {stderr}")

                # 5. Determine if connection succeeded: successful connection returns "Connection handle"
                if "Connection handle" in stdout:
                    thread_terminal_logging("uut", "info", f"Connection successful")
                    return True
                # Handle common connection failure cases
                elif "Could not create connection" in stderr:
                    thread_terminal_logging("uut", "error", f"Connection failed:{stderr.strip()}")
                elif "Connection timed out" in stderr:
                    thread_terminal_logging("uut", "error", f"Connection timed out: {stderr.strip()}")
                else:
                    # Unknown state: use return code for auxiliary judgment
                    thread_terminal_logging("uut", "warning", f"Unknown connection state: return_code={return_code}")

                return False  # Return False for connection failure

            except Exception as e:
                thread_terminal_logging("uut", "error", f"Error connecting to device: {e}")
                return False

        return self._retry_operation(_connect_impl, "connect device")

    def run(self):
        """Perform complete BLE connection process: acquire lock->connect to device->release lock"""
        thread_terminal_logging("uut", "info", f"=== Starting BLE device connection: {self.ble_mac_address} ===")

        try:
            # 1. Acquire operation lock: prevent concurrent operation on Bluetooth adapter by multiple processes
            self.lock_file = self.acquire_lock()
            if not self.lock_file:
                thread_terminal_logging("uut",
                                        "warning",
                                        f"Warning: Could not acquire lock, proceeding(proceeding concurrency risk")

            # 2. Connect to device using acquired MAC address
            self.connection_success = self.connect_device(self.ble_mac_address)
            if self.connection_success:
                thread_terminal_logging("uut","info", f"BLE device connection successful, process completed")
                return True   # return True indicates that the entire process is successful
            else:
                thread_terminal_logging("uut", "error", f"Connection to device {self.ble_mac_address} failed")
                return False  # Return false to indicate connection failure

        except Exception as e:
            # Catch unexpected exceptions in connection process
            thread_terminal_logging("uut", "error", f"Exception in main connection process: {e}")
            return False
        finally:
            # 4. Release lock regardless of connection success/failure/exception (avoid lock leftover)
            self.release_lock()
            thread_terminal_logging("uut", "info", f"===BLE Connection process completed ===")

    def get_connection_result(self):
        """Get final BLE connection result: returns dictionary containing connection status, device MAC, and adapter name"""
        return {
            "success": self.connection_success,
            "mac_address": self.ble_mac_address,
            "hci_device": self.hci_device
        }

