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
import logging
import select
from datetime import datetime
import fcntl
from collections import Counter  # For counting statistics


class BLEConnector:
    """Encapsulates BLE connection functionality for device wake-up in reliability testing"""

    def __init__(self, ble_device_name, max_retries=3, logger=None):
        """
        Initialize BLE connector
        :param ble_device_name: Target BLE device name (must match actual device broadcast name)
        :param max_retries: Maximum number of retries (default 3, for retry after failed operations like scanning, connecting)
        :param logger: Optional external logger (creates internal one if not provided)
        """
        # Initialize core parameters
        self.ble_device_name = ble_device_name  # Target BLE device name, used for matching during scanning
        self.max_retries = max_retries  # Default maximum retry count for all retryable operations

        # Configure logging system: prefer externally provided logger, create internal one if none
        self.logger = logger or self._setup_logger()

        # Automatically detect USB Bluetooth adapter in the system (exclude virtual devices to ensure hardware validity)
        self.hci_device = self._detect_usb_bluetooth_dongle()
        self.logger.info(f"Using Bluetooth adapter: {self.hci_device}")

        # Connection process state tracking variables
        self.connection_success = False
        self.lock_file = None
        self.ble_mac = None
        self.scan_process = None
        self.lock_fd = None  # Used to store the file descriptor

        # Ensure Bluetooth adapter is available during initialization, exit if unavailable
        if not self.ensure_adapter_ready():
            self.logger.error("Bluetooth adapter unavailable, exiting program")
            sys.exit(1)

    def _setup_logger(self):
        """Configure logger: output to both console (INFO level) and file (DEBUG level)"""
        # Create logger instance with name "BLEConnector"
        logger = logging.getLogger("BLEConnector")
        logger.setLevel(logging.INFO)

        # Clear existing log handlers (prevent duplicate logging from multiple handlers)
        if logger.hasHandlers():
            for handler in logger.handlers[:]:
                logger.removeHandler(handler)
                handler.close()  # Close handler to release resources

        # Define log format: includes timestamp, log level, and message
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(name)s - %(message)s',  # Fixed: added space after %(name)s
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # 1. Create console log handler (outputs INFO and above level logs to terminal)
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

        # 2. Create file log handler (outputs DEBUG and above level logs to file for later debugging)
        log_file = f"ble_connector_{datetime.now().strftime('%Y%m%d')}.log"  # Log filename includes date
        fh = logging.FileHandler(log_file)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

        return logger  # return the configure logger

    def _detect_usb_bluetooth_dongle(self):
        """Automatically detect external USB Bluetooth dongle - Simplified version"""
        try:
            # Get Bluetooth device information using hciconfig command
            result = subprocess.run(['hciconfig'], capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                self.logger.error("Failed to retrieve Bluetooth device information")
                sys.exit(1)

            # Parse devices and calculate confidence scores
            devices = []
            current_device = None

            for line in result.stdout.split('\n'):
                # Detect device line (e.g., "hci0: Type: Primary Bus: USB")
                if ':' in line and line.strip().startswith('hci'):
                    parts = line.split(':')
                    current_device = {
                        'name': parts[0].strip(),
                        'is_usb': 'Bus: USB' in line,  # Check if it's a USB device
                        'score': 0  # Confidence score for external dongle detection
                    }
                    devices.append(current_device)

                # Score devices based on characteristics (only for USB devices)
                elif current_device and current_device['is_usb']:
                    # Running devices are preferred
                    if 'UP RUNNING' in line:
                        current_device['score'] += 10

                    # Check if device is not the built-in one (heuristic approach)
                    # Built-in Bluetooth often has specific patterns in the output
                    if 'PSCAN' in line and 'ISCAN' not in line:
                        # This is often a characteristic of built-in Bluetooth
                        current_device['score'] -= 5

            # Filter only USB devices (exclude virtual/non-USB devices)
            usb_devices = [d for d in devices if d['is_usb']]

            if not usb_devices:
                self.logger.error("No USB Bluetooth dongle found")
                sys.exit(1)

            # If only one USB device, select it
            if len(usb_devices) == 1:
                selected_device = usb_devices[0]['name']
                self.logger.info(f"Selected the only USB Bluetooth device: {selected_device}")
                return selected_device

            # If multiple USB devices, select the one with highest score
            best_device = max(usb_devices, key=lambda x: x['score'])
            self.logger.info(
                f"Selected Bluetooth device: {best_device['name']} (confidence score: {best_device['score']})")

            return best_device['name']

        except Exception as e:
            self.logger.error(f"Error detecting USB Bluetooth dongle: {e}")
            sys.exit(1)

    def _run_command(self, cmd, timeout=30):
        """
        Universal system command execution function: supports timeout control, real-time logging, returns command execution results
        :param cmd: System command to execute (string format, e.g., "hciconfig hci0 up")
        :param timeout: Command execution timeout in seconds (default 30)
        :return: stdout (command standard output), stderr (command error output), return_code (return code), timed_out (whether timeout occurred)
        """
        self.logger.debug(
            f"Executing command: {cmd}")  # Log command to execute (DEBUG level, only visible in file logs)

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
                                self.logger.debug(f"STDOUT: {line}")
                                outputs["stdout"].append(line)
                            else:
                                self.logger.debug(f"STDERR: {line}")
                                outputs["stderr"].append(line)
                        else:  # Empty line indicates stream closed (EOF), remove from monitoring list
                            fds.remove(fd)
                    except Exception as e:
                        self.logger.warning(f"Error reading output: {e}")
                        if fd in fds:
                            fds.remove(fd)

            # Handle command timeout: terminate subprocess and clean up resources
            if timed_out:
                process.terminate()  # First try graceful termination
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                self.logger.error(f"Command timed out: {cmd}")
                return "", "Command execution timed out", -1, True

            # Command completed normally, get process return code
            return_code = process.wait()

            # Combine output lists into strings (join lines with newlines)
            stdout = "\n".join(outputs["stdout"])
            stderr = "\n".join(outputs["stderr"])

            self.logger.debug(f"Command return code: {return_code}")
            return stdout, stderr, return_code, False  # Return normal execution results

        except Exception as e:
            # Catch exceptions during command execution (e.g., failed to create subprocess)
            self.logger.error(f"Command execution exception: {e}")
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
                self.logger.info(f"Performing {operation_name} (attempt {attempt}/{max_retries})")

                # Call target function with positional and keyword arguments
                result = operation_func(*args, **kwargs)

                # Determine if operation succeeded: result is considered successful if not False or None (different operations have different return values)
                if result is not False and result is not None:
                    return result  # Success, return result

                # Operation failed and not reached maximum retries, calculate wait time and retry
                if attempt < max_retries:
                    wait_time = min(2 ** attempt, 30)  # Exponential backoff: 2^attempt seconds, maximum 30 seconds
                    self.logger.info(f"Waiting {wait_time} seconds before retry")
                    time.sleep(wait_time)  # Wait for specified time

            except Exception as e:
                # Catch exceptions during target function execution (e.g., file read errors during scanning)
                self.logger.error(f"Error performing {operation_name}: {e}")
                # Wait and retry if not reached maximum retries
                if attempt < max_retries:
                    wait_time = min(2 ** attempt, 30)
                    self.logger.info(f"Waiting {wait_time} seconds before retry")
                    time.sleep(wait_time)

        # All retry attempts exhausted with failure
        self.logger.error(f"Error: Exceeded maximum retry count {max_retries}")
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
                    self.logger.info(f"Adapter {self.hci_device} reset successful")
                    return True  # single reset successful
                else:
                    self.logger.warning(f"Adapter state abnormal: {stdout}")
                    return False # exception occurred,reset failed

            except Exception as e:
                self.logger.error(f"Error resetting adapter: {e}")
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
                    self.logger.info(f"Adapter {self.hci_device} is already enabled")
                    return True

                # 2. Adapter not active, attempt activation with up command
                self.logger.warning(f"Adapter {self.hci_device} not enabled, attempting activation...")
                self._run_command(f"sudo hciconfig {self.hci_device} up")
                time.sleep(2)  # wait for 2 seconds to ensure activation is complete

                # 3. Check state again after activation
                stdout, _, _, _ = self._run_command(f"hciconfig {self.hci_device}")
                if "UP RUNNING" in stdout:
                    self.logger.info(f"Adapter {self.hci_device} activation successful")
                    return True # activation successful
                else:
                    self.logger.warning(f"Adapter state after activation: {stdout}")
                    return False  # abnormal Status after activation，failed

            except Exception as e:
                self.logger.error(f"Error checking adapter state: {e}")
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
                    self.logger.info(f"Created lock file: {lock_file}")
                    self.lock_fd = fd  # Save file descriptor for subsequent release
                    return lock_file

                except BlockingIOError:
                    # Lock is held by another process, enter waiting logic
                    self.logger.info("Lock is held by another process, waiting...")

                    start_time = time.time()
                    # Retry every 0.1 seconds until timeout (balances response speed and CPU usage)
                    while time.time() - start_time < max_wait:
                        try:
                            # Retry acquiring the non-blocking exclusive lock
                            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                            os.ftruncate(fd, 0)  # Clear file content
                            os.write(fd, str(os.getpid()).encode())  # Write current process PID
                            self.logger.info(f"Created lock file: {lock_file}")
                            self.lock_fd = fd
                            return lock_file

                        except BlockingIOError:
                            time.sleep(0.1)  # Short delay to reduce CPU consumption

                    # Timeout occurred, clean up resources
                    os.close(fd)  # Close file descriptor to avoid leakage
                    self.logger.warning(f"Lock waiting timed out ({max_wait}s), proceeding forcefully")
                    return None

            except Exception as e:
                self.logger.error(f"Failed to acquire lock: {e}")
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
                self.logger.info("Successfully released fcntl lock")
            except Exception as e:
                self.logger.error(f"Failed to release fcntl lock: {e}")

        # Delete the lock file (retain original cleanup logic)
        if self.lock_file and os.path.exists(self.lock_file):
            try:
                os.remove(self.lock_file)  # Delete the lock file to avoid residual files
                self.logger.info(f"Released lock file: {self.lock_file}")
                self.lock_file = None  # Reset to indicate no lock file exists
            except Exception as e:
                self.logger.error(f"Failed to release lock file: {e}")
        else:
            self.logger.info("No lock file to release")

    def scan_device(self):
        """Scan for BLE devices: monitor scan results in real-time, stop immediately when target device name is found, return device MAC address"""
        scan_file = None  # Define variable at function level

        def _scan_impl():
            nonlocal scan_file  # Use nonlocal to modify the outer variable
            # Precompile MAC address regular expression: matches BLE device MAC format (xx:xx:xx:xx:xx:xx, case-insensitive)
            mac_pattern = re.compile(r"((?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}) (.*)")

            try:
                # 1. First stop all possible remaining hcitool processes (avoid interfering with current scan)
                self._run_command("sudo pkill -f hcitool", timeout=5)
                time.sleep(2)  # Wait 2 seconds to ensure processes terminate

                # 2. Reset adapter (clean previous scan state, improve scan success rate)
                self.reset_adapter()
                time.sleep(2)

                # 3. Create temporary scan file: stores output of lescan command (inter-process data sharing)
                scan_file = f"ble_scan_{os.getpid()}_{int(time.time())}.txt"

                # 4. Start BLE scanning process: lescan command (--duplicates keeps duplicate scan results for signal strength judgment)
                scan_cmd = f"sudo hcitool -i {self.hci_device} lescan --duplicates > {scan_file} 2>&1"
                self.scan_process = subprocess.Popen(
                    scan_cmd,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                # 5. Configure scan timeout and result monitoring
                scan_timeout = 30
                start_time = time.time()
                found_device = None

                # Monitor scan file in real-time to find target device
                while time.time() - start_time < scan_timeout:
                    # Check if scan process exited unexpectedly (terminated before timeout)
                    if self.scan_process.poll() is not None:
                        break
                    # Check if temporary scan file exists (process startup may have delay)
                    if os.path.exists(scan_file):
                        try:
                            # Read current content of scan file
                            with open(scan_file, 'r', errors='ignore') as f:
                                content = f.read()

                            # Parse scan results line by line to match target device
                            lines = content.splitlines()
                            for line in lines:
                                # Extract MAC address and device name with regular expression
                                match = mac_pattern.match(line)
                                if match and self.ble_device_name in match.group(2):
                                    # Target device found: extract MAC address
                                    found_device = match.group(1)
                                    self.logger.info(
                                        f"Found device in real-time: {self.ble_device_name} MAC: {found_device}")
                                    # Stop scan process immediately after finding device
                                    self.scan_process.terminate()
                                    try:
                                        self.scan_process.wait(timeout=2)
                                    except subprocess.TimeoutExpired:
                                        self.scan_process.kill()
                                    return found_device

                        except Exception as e:
                            self.logger.warning(f"Error reading scan file: {e}")

                    time.sleep(0.5)  # Check scan results every 0.5 seconds, balance real-time performance and CPU usage

                # 6. Scan timeout: stop scan process (prevent process leftover)
                if self.scan_process.poll() is None:
                    self.scan_process.terminate()
                    try:
                        self.scan_process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self.scan_process.kill()

                # 7. Check scan file again after timeout (device might be scanned at the last moment)
                if os.path.exists(scan_file):
                    try:
                        with open(scan_file, 'r') as f:
                            content = f.read()

                        # Collect all scan results matching target device name (MAC + device name)
                        matches = []
                        for line in content.splitlines():
                            match = mac_pattern.match(line)
                            if match and self.ble_device_name in match.group(2):
                                matches.append((match.group(1), match.group(2)))
                                self.logger.debug(f"Found matching device: {match.group(1)} - {match.group(2)}")

                        # If multiple matching results, select MAC with most occurrences (strongest signal, scanned most times)
                        if matches:
                            mac_counter = Counter(mac for mac, _ in matches)  # Count MAC occurrences
                            ble_mac = mac_counter.most_common(1)[0][0]  # Get MAC with most occurrences
                            self.logger.info(f"Scan completed, found device: {self.ble_device_name} MAC: {ble_mac}")
                            return ble_mac   # return BLE MAC

                    except Exception as e:
                        self.logger.error(f"Failed to read scan file: {e}")

                # 8. Target device not found
                self.logger.warning(f"Device not found: {self.ble_device_name}")
                return False

            except Exception as e:
                self.logger.error(f"Error scanning for device: {e}")
                return False
            finally:
                # Ensure cleanup of leftover processes and temporary files regardless of scan success/failure/exception
                self._run_command("sudo pkill -f hcitool", timeout=5)

        try:
            return self._retry_operation(_scan_impl, "scan device")
        finally:
            # Ensure temporary scan file is deleted
            if scan_file and os.path.exists(scan_file):
                try:
                    os.remove(scan_file)
                    self.logger.debug(f"Deleted temporary scan file: {scan_file}")
                except Exception as e:
                    self.logger.warning(f"Failed to delete scan file {scan_file}: {e}")

    def connect_device(self, ble_mac):
        """Perform BLE device connection: use hcitool lecc command to connect to target device (requires MAC address)"""

        # Internal implementation function: encapsulates connection logic
        def _connect_impl():
            # First check if MAC address is valid (avoid connection failure due to invalid parameters)
            if not ble_mac:
                self.logger.error("Invalid MAC address, skipping connection")
                return False

            try:
                # 1. Stop all Bluetooth-related processes (clean up previous connection leftovers)
                self.logger.info("Stopping all Bluetooth-related processes")
                self._run_command("sudo pkill -f hcitool", timeout=5)
                time.sleep(2)

                # 2. Reset adapter (restore initial state, resolve connection leftover issues)
                self.logger.info("Resetting Bluetooth adapter state")
                self._run_command(f"sudo hciconfig {self.hci_device} reset", timeout=10)
                time.sleep(2)

                # 3. Execute BLE connection command: lecc (LE Connection Command)
                self.logger.info(f"Connecting to device {ble_mac} using hcitool")
                cmd = f"sudo timeout 30 hcitool -i {self.hci_device} lecc --random {ble_mac}"
                # Execute command with timeout set to 35 seconds (5 seconds more than internal command timeout to avoid false timeout judgment)
                stdout, stderr, return_code, timed_out = self._run_command(cmd, timeout=35)

                # 4. Record detailed connection command results (for debugging)
                self.logger.debug(f"Connection command results: timed_out={timed_out}, return_code={return_code}")
                self.logger.debug(f"STDOUT: {stdout}")
                self.logger.debug(f"STDERR: {stderr}")

                # 5. Determine if connection succeeded: successful connection returns "Connection handle"
                if "Connection handle" in stdout:
                    self.logger.info("Connection successful!")
                    return True
                # Handle common connection failure cases
                elif "Could not create connection" in stderr:
                    self.logger.error(f"Connection failed: {stderr.strip()}")
                elif "Connection timed out" in stderr:
                    self.logger.error(f"Connection timed out: {stderr.strip()}")
                else:
                    # Unknown state: use return code for auxiliary judgment
                    self.logger.warning(f"Unknown connection state: return_code={return_code}")

                return False  # Return False for connection failure

            except Exception as e:
                self.logger.error(f"Error connecting to device: {e}")
                return False

        return self._retry_operation(_connect_impl, "connect device")

    def run(self):
        """Perform complete BLE connection process: acquire lock->scan for device->connect to device->release lock"""
        self.logger.info(f"=== Starting BLE device connection: {self.ble_device_name} ===")

        try:
            # 1. Acquire operation lock: prevent concurrent operation on Bluetooth adapter by multiple processes
            self.lock_file = self.acquire_lock()
            if not self.lock_file:
                self.logger.warning("Warning: Could not acquire lock, proceeding (potential concurrency risk)")

            # 2. Scan for target device to get MAC address (cannot connect without MAC address)
            self.ble_mac = self.scan_device()
            if not self.ble_mac:
                self.logger.error("Could not find device MAC address, connection process terminated")
                return False  # return False to indicate scan failure,unable to continue connection

            # 3. Connect to device using acquired MAC address
            self.connection_success = self.connect_device(self.ble_mac)
            if self.connection_success:
                self.logger.info("BLE device connection successful, process completed")
                return True   # return True indicates that the entire process is successful
            else:
                self.logger.error("Found device MAC address but connection failed")
                return False  # Return false to indicate connection failure

        except Exception as e:
            # Catch unexpected exceptions in connection process
            self.logger.error(f"Exception in main connection process: {e}")
            return False
        finally:
            # 4. Release lock regardless of connection success/failure/exception (avoid lock leftover)
            self.release_lock()
            self.logger.info("=== BLE connection process completed ===")

    def get_connection_result(self):
        """Get final BLE connection result: returns dictionary containing connection status, device MAC, and adapter name"""
        return {
            "success": self.connection_success,
            "mac_address": self.ble_mac,
            "hci_device": self.hci_device
        }

