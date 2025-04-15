#!/home/delt/asvz_bot/asvz_bot/bin/python

"""
Created on: Mar 20, 2019
Author: Julian Stiefel
Edited: Patrick Barton and Matteo Delucchi, October 2020
License: BSD 3-Clause
Description: Script for automatic enrollment in ASVZ classes
"""

import time
import math
import argparse
import asyncio
import configparser
import telegram_send
import geckodriver_autoinstaller
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
# from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException

day2int = {'Montag': 0,
           'Dienstag': 1,
           'Mittwoch': 2,
           'Donnerstag': 3,
           'Freitag': 4,
           'Samstag': 5,
           'Sonntag': 6}


def waiting_fct():
    def get_lesson_datetime(day, train_time):
        # find next date with that weekday
        nextDate = datetime.today().date()
        while nextDate.weekday() != day2int[day]:
            nextDate += timedelta(days=1)

        # combine with training time for complete date and time object
        lessonTime = datetime.strptime(train_time, '%H:%M').time()
        return datetime.combine(nextDate, lessonTime)

    lessonTime = get_lesson_datetime(config['lesson']['day'], config['lesson']['lesson_time'])
    enrollmentTime = lessonTime - timedelta(hours=config['lesson'].getint('enrollment_time_difference'))

    # Wait till enrollment opens if script is started before registration time
    delta = enrollmentTime - datetime.today()
    while delta > timedelta(seconds=60):
        print("Time till enrollment opens: " + str(delta))
        if delta < timedelta(minutes=1):
            time.sleep(math.ceil(delta.total_seconds()))
        elif delta < timedelta(minutes=5):
            time.sleep(60)
        elif delta < timedelta(hours=1):
            time.sleep(5*60)
        else:
            time.sleep(60*60)
        delta = enrollmentTime - datetime.today()
    return


def login_switchai(driver):
    # Check whether we have to login
    login_button_locator = (By.XPATH, "//button[@class='btn btn-default' and @title='Login']")

    try:
        login_visible = WebDriverWait(driver, args.max_wait).until(EC.visibility_of_element_located(login_button_locator))
        if not login_visible:
            print("Probably already logged in")
            return True
    except:
        print("Probably already logged in")
        return True

    WebDriverWait(driver, args.max_wait).until(EC.element_to_be_clickable(
        (By.XPATH, "//button[@class='btn btn-default' and @title='Login']"))).click()
    WebDriverWait(driver, args.max_wait).until(EC.element_to_be_clickable(
        (By.XPATH, "//button[@class='btn btn-warning btn-block' and @title='SwitchAai Account Login']"))).click()

    # choose organization:
    organization = driver.find_element("xpath", "//input[@id='userIdPSelection_iddtext']")
    organization.send_keys(config['creds']['organisation'])
    organization.send_keys(u'\ue006')

    driver.find_element("xpath", "//input[@id='username']").send_keys(config['creds']['username'])
    driver.find_element("xpath", "//input[@id='password']").send_keys(config['creds']['password'])
    driver.find_element("xpath", "//button[@type='submit']").click()
    print('Logged in')


def find_training_and_open_url(driver):
    print('Attempting to get sportfahrplan')
    print(config['lesson']['sportfahrplan_particular'])
    driver.get(config['lesson']['sportfahrplan_particular'])
    driver.implicitly_wait(5)  # wait 5 seconds if not defined differently
    print("Sportfahrplan retrieved")

    # find corresponding day div:
    day_ele = driver.find_element("xpath", 
        "//div[@class='teaser-list-calendar__day'][contains(., '" + config['lesson']['day'] + "')]")

    # search in day div after corresponding location and time
    lesson_xpath = ".//li[@class='btn-hover-parent'][contains(., '" + config['lesson']['facility'] + "')][contains(., '" \
                        + config['lesson']['lesson_time'] + "')]"
    if config['lesson']['description']:
        lesson_xpath += "[contains(., '" + config['lesson']['description'] + "')]"

    try:
        lesson_ele = day_ele.find_element("xpath", lesson_xpath)
    except NoSuchElementException as identifier:
        # click on "load more" button
        driver.find_element("xpath", "//button[@class='btn btn--primary separator__btn']").click()
        lesson_ele = day_ele.find_element("xpath", lesson_xpath)

    
    # check if the lesson is already booked out
    # full = len(lesson_ele.find_elements("xpath", ".//div[contains(text(), 'Keine freien')]"))
    # if full:
    #     print('Lesson already fully booked. Retrying in ' + str(args.retry_time) + 'min')
    #     driver.quit()
    #     time.sleep(args.retry_time * 60)
    #     return False

    # Save Lesson information for Telegram Message
    message = lesson_ele.text
    print("Booking: ", message)
    lesson_ele.click()

    return message

def asvz_enroll(args):
    print('Starting browser')
    options = Options()
    # options.headless = True
    options.add_argument('--headless')
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--private")  # open in private mode to avoid different login scenario
    driver = webdriver.Chrome(options=options)

    message = find_training_and_open_url(driver)

    # Login if needed
    login_switchai(driver)

    while True:
        result = attemp_enroll(driver)
        if result == True:
            driver.quit()
            return message
        time.sleep(args.retry_time * 60)
        driver.refresh()

        
def attemp_enroll(driver):
    enroll_button_locator = (By.XPATH, "//button[@id='btnRegister']")    
    try:
        WebDriverWait(driver, args.max_wait).until(EC.visibility_of_element_located(enroll_button_locator))
    except:
        print('Element not visible. Probably fully booked. Retrying in ' + str(args.retry_time) + 'min')
        return False

    print('Waiting for enroll button to be enabled')
    try:
        enroll_button = WebDriverWait(driver, 2).until(EC.element_to_be_clickable(enroll_button_locator))
        enroll_button.click()
        time.sleep(3)
    except:
        raise ('Enroll button is disabled. Enrollment is likely not open yet.')
        # return False

    print("Successfully enrolled. Have fun!")
    return True


async def send_telegram_msg(msg):
    await telegram_send.send(messages=[msg])


def main():
    waiting_fct()

    # If lesson is already fully booked keep retrying in case place becomes available again
    success = False
    while not success:
        try:
            success = asvz_enroll(args)
        except:
            if args.telegram_notifications:
                asyncio.run(send_telegram_msg('Script stopped. Exception occurred :('))
            raise

    if args.telegram_notifications:
        telegram_send.send(messages=['Enrolled successfully :D', "------------", success])
    print("Script finished successfully")

if __name__ == "__main__":
    # ==== run enrollment script ============================================

    # Check if the current version of geckodriver exists
    # and if it doesn't exist, download it automatically,
    # then add geckodriver to path
    geckodriver_autoinstaller.install()

    parser = argparse.ArgumentParser(description='ASVZ Bot script')
    parser.add_argument('config_file', type=str, help='config file name')
    parser.add_argument('--retry_time', type=float, default=0.33,
                        help='Time between retrying when class is already fully booked in minutes')
    parser.add_argument('--max_wait', type=int, default=5, help='Max driver wait time (s) when attempting an action')
    parser.add_argument('-t', '--telegram_notifications', action='store_false', help='Whether to use telegram-send for notifications')
    args = parser.parse_args()

    config = configparser.ConfigParser(allow_no_value=True)
    config.read(args.config_file)
    config.read('credentials.ini')

    main()