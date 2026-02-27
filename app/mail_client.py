# Improved AppleScript and Logging
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def execute_applescript(script):
    try:
        logging.info('Executing AppleScript...')
        # Execute the AppleScript
        os.system(f"osascript -e '{script}'")
        logging.info('AppleScript executed successfully.')
    except Exception as e:
        logging.error(f'Error executing AppleScript: {e}')

# Example usage
if __name__ == '__main__':
    script = 'tell application "Finder" to activate'
    execute_applescript(script)