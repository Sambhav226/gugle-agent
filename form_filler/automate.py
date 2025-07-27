from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager # Import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import json
import os
import argparse
from datetime import datetime 

print("--- automate.py execution started ---")

# --- Setup Argument Parser ---
parser = argparse.ArgumentParser(description="Automate filling a specific grievance form.")
parser.add_argument('--form_filename', type=str, required=True,
                    help='The filename of the HTML form to fill (e.g., infrastructure_form.html)')
args = parser.parse_args()
target_form_filename = args.form_filename
print(f"Target form filename from argument: {target_form_filename}")

# --- Selenium Options ---
options = Options()
# options.add_argument('--headless') # Commented out or remove this line to see the browser
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--window-size=1280,1024') # You can adjust window size
options.add_argument("start-maximized") # To start maximized
# options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")


print("Initializing ChromeDriver using webdriver-manager for automate.py...")
driver = None 
try:
    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(20) 
    print("ChromeDriver initialized successfully.")

    # --- Load Input Data ---
    input_values = {}
    json_file_path = "form_data_to_fill.json" 
    print(f"Attempting to load input data from: {os.path.abspath(json_file_path)}")

    if os.path.exists(json_file_path):
        try:
            with open(json_file_path, 'r') as f:
                input_values = json.load(f)
            print(f"Loaded input_values: {json.dumps(input_values, indent=2)}")
        except Exception as e:
            print(f"Error loading {json_file_path}: {e}. Proceeding with empty input_values.")
    else:
        print(f"Error: {json_file_path} not found. Proceeding with empty input_values.")

    # --- Determine Form URL ---
    current_script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root_dir_guess = os.path.dirname(current_script_dir) 
    form_templates_dir = os.path.join(project_root_dir_guess, "form_templates")
    
    target_form_path = os.path.join(form_templates_dir, target_form_filename)
    absolute_target_form_path = os.path.abspath(target_form_path)
    print(f"Calculated absolute path for target form: {absolute_target_form_path}")

    if not os.path.exists(absolute_target_form_path):
        print(f"Error: Target form HTML file not found at {absolute_target_form_path}")
        if driver: driver.quit()
        exit(1) 

    form_url = f"file://{absolute_target_form_path}"
    
    print(f"Navigating to form URL: {form_url}")
    try:
        driver.get(form_url)
    except TimeoutException:
        print(f"Timeout loading page: {form_url}. Check if the file path is correct and accessible.")
        if driver: driver.quit()
        exit(1)
        
    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "form")))
        print("Form element located. Page seems loaded.")
    except TimeoutException:
        print("Timed out waiting for form element to load.")
        if driver: driver.quit()
        exit(1)

    print("Attempting to fill form fields...")
    filled_count = 0
    if not input_values:
        print("No input values loaded, cannot fill form.")
    else:
        for field_key_from_voice, value_to_fill in input_values.items():
            form_field_name = field_key_from_voice 
            if value_to_fill is None or (isinstance(value_to_fill, str) and not value_to_fill.strip()):
                print(f"Skipping field '{form_field_name}' due to empty or None value.")
                continue
            try:
                input_element = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.NAME, form_field_name)))
                element_type = input_element.get_attribute("type"); tag_name = input_element.tag_name.lower()
                print(f"Attempting: NAME='{form_field_name}', Value='{value_to_fill}', Type='{element_type}', Tag='{tag_name}'")

                if tag_name == "select":
                    select = Select(input_element); selected_successfully = False
                    try: 
                        select.select_by_value(str(value_to_fill)); selected_successfully = True
                    except NoSuchElementException:
                        try: 
                            select.select_by_visible_text(str(value_to_fill)); selected_successfully = True
                        except NoSuchElementException:
                            for option in select.options:
                                if str(value_to_fill).lower() in option.text.lower():
                                    select.select_by_visible_text(option.text)
                                    print(f"Selected '{option.text}' by partial match for '{form_field_name}'."); selected_successfully = True; break
                            if not selected_successfully: print(f"No match for '{value_to_fill}' in select '{form_field_name}'. Options: {[opt.text for opt in select.options]}")
                    if not selected_successfully: continue
                elif element_type in ["text", "email", "tel", "date", "number"] or tag_name == "textarea":
                    input_element.clear(); input_element.send_keys(str(value_to_fill))
                elif element_type == "checkbox":
                    is_true = str(value_to_fill).lower() == 'true' or value_to_fill is True
                    # Ensure element is clickable before interacting
                    WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.NAME, form_field_name)))
                    if is_true != input_element.is_selected(): input_element.click()
                else: print(f"Skipping '{form_field_name}', unhandled type/tag: Type '{element_type}', Tag '{tag_name}'.")
                filled_count +=1
            except TimeoutException: print(f"Timed out for field NAME='{form_field_name}'.")
            except NoSuchElementException: print(f"Field NAME='{form_field_name}' not found.")
            except Exception as e_field: print(f"Error filling field '{form_field_name}': {e_field}")
        print(f"Filled {filled_count} fields.")

    try:
        submit_button = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']")))
        submit_button.click(); print("Clicked submit button.")
    except Exception as e_submit: print(f"Error clicking submit button: {e_submit}")

    print("Form filling process completed. Browser will remain open for a few seconds...")
    time.sleep(100) # Keep browser open for 10 seconds to see the result
    
except Exception as e:
    print(f"An critical error occurred in automate.py: {e}")
    if driver:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_file = f"error_screenshot_{timestamp}.png" 
        try:
            driver.save_screenshot(screenshot_file)
            print(f"Screenshot saved to {os.path.abspath(screenshot_file)}")
        except Exception as se: print(f"Could not save screenshot: {se}")
    exit(1) 
finally:
    if driver: print("Quitting WebDriver."); driver.quit()
    print("--- automate.py execution finished ---")