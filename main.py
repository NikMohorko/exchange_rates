from flask import Flask
import requests
from google.cloud import logging
from google.cloud import secretmanager
from google.oauth2 import service_account
import json
from datetime import datetime, timedelta
from pandas import read_json as json_to_dataframe
from io import StringIO
import os
from shutil import rmtree
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import ssl
import smtplib

app = Flask(__name__)


@app.route('/', methods=['POST'])
def main():

    def get_exchange_rates(currencies: list, date: str):
        """Requests daily exchange rate between each currency and EUR from SDMX web service."""

        exchange_rates_output = {}

        for currency in currencies:
            for retry in range(3):
                try:
                    url = ''.join(['https://sdw-wsrest.ecb.europa.eu/service/data/EXR/D.', currency,
                                   '.EUR.SP00.A?startPeriod=', date, '&endPeriod=', date, '&format=jsondata'])

                    exchange_rate_response = requests.get(url, timeout=20)

                    # Try with alternative date if today is not available yet
                    if not exchange_rate_response.text:

                        date = get_alternative_date()

                        url = ''.join(['https://sdw-wsrest.ecb.europa.eu/service/data/EXR/D.', currency,
                                       '.EUR.SP00.A?startPeriod=', date, '&endPeriod=', date, '&format=jsondata'])

                        exchange_rate_response = requests.get(url, timeout=20)

                    exchange_rate_response = exchange_rate_response.json()

                    exchange_rates_output['to'.join([currency, 'EUR'])] = float(
                        exchange_rate_response['dataSets'][0]['series']['0:0:0:0:0']['observations']['0'][0])

                except requests.Timeout:
                    logger.log_text('Request for ' + currency + ' exchange rate timed out.', severity='ERROR')

                except requests.ConnectionError:
                    logger.log_text('Request for ' + currency +
                                    ' exchange rate failed due to connection error.', severity='ERROR')

                except KeyError:
                    logger.log_text('Request for ' + currency + ' failed - response structure has changed.',
                                    severity='ERROR')
                    break

                else:
                    logger.log_text('Request for ' + currency + ' exchange rate successful.', severity='INFO')
                    break

        return exchange_rates_output, date

    def send_email(receiver: str, sender_smtp_address: str, sender_smtp_port: int, sender_email: str,
                   sender_password: str, subject: str, body: str, attachment_path: str):

        message = MIMEMultipart()
        message['From'] = sender_email
        message['Subject'] = subject
        message['To'] = receiver
        message.attach(MIMEText(body, 'plain'))

        with open(attachment_path, 'rb') as att_file:
            part = MIMEBase(
                'application',
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            part.set_payload(att_file.read())

        encoders.encode_base64(part)

        part.add_header(
            'Content-Disposition',
            'attachment; filename=exchange_rates.xlsx',
        )

        message.attach(part)
        email_text_content = message.as_string()
        ssl_context = ssl.create_default_context()

        try:
            with smtplib.SMTP_SSL(sender_smtp_address, sender_smtp_port, context=ssl_context) as server:
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, receiver, email_text_content)

        except Exception as exc:
            logger.log_text(''.join(['Sending e-mail to ', receiver, ' failed with exception: ', str(exc)]),
                            severity='ERROR')
            return False

        else:
            logger.log_text(''.join(['E-mail to ' + receiver + ' successfully sent.']), severity='INFO')
            return True

    def load_service_account_credentials():
        """Checks if service account file exists and loads credentials when service is ran locally."""

        if use_locally:
            if not os.path.isfile('service_account.json'):
                print('Service account file is missing.')
                return None

            else:
                with open('service_account.json', 'r') as s:
                    service_acc_data = json.load(s)

                return service_account.Credentials.from_service_account_info(service_acc_data)

        else:
            return None

    def get_alternative_date():
        """Determines last workday as an alternative for getting exchange rates"""

        previous_day = datetime.now() - timedelta(days=1)
        while previous_day.weekday() > 4:
            previous_day -= timedelta(days=1)

        return previous_day.strftime('%Y-%m-%d')

    with open('config.json', 'r') as f:
        settings = json.load(f)
        use_locally = settings['use_locally']

    response_200 = app.response_class(status=200)
    response_500 = app.response_class(status=500)

    if use_locally:
        temp_path = 'temp/'
    else:
        temp_path = '/tmp/'

    service_account_credentials = load_service_account_credentials()
    if use_locally and service_account_credentials is None:
        return response_500

    logging_client = logging.Client(credentials=service_account_credentials)
    logger = logging_client.logger('exchange_rates')

    secrets_client = secretmanager.SecretManagerServiceClient(credentials=service_account_credentials)
    secret_content = secrets_client.access_secret_version(
        name='projects/{}/secrets/email_password/versions/latest'.format(settings['gcp_project_id']))
    email_password = secret_content.payload.data.decode('UTF-8')

    date_today = datetime.today().strftime('%Y-%m-%d')
    exchange_rates, actual_date = get_exchange_rates(settings['currencies'], date_today)

    if not os.path.exists(temp_path):
        os.mkdir(temp_path)

    dataframe = json_to_dataframe(StringIO(json.dumps([exchange_rates])))
    dataframe.to_excel(''.join([temp_path, 'exchange_rates.xlsx']), index=False)

    email_sent = send_email(
        settings['target_email_address'],
        settings['sender_email_smtp_address'],
        int(settings['sender_email_smtp_port']),
        settings['sender_email_address'],
        email_password,
        ''.join(['Exchange rates on ', actual_date]),
        '',
        ''.join([temp_path, 'exchange_rates.xlsx'])
    )

    # Clean up temp directory
    if use_locally and os.path.exists(temp_path):
        rmtree(temp_path)

    else:
        for temp_file in os.listdir(temp_path):
            if os.path.isfile(os.path.join(temp_path, temp_file)):
                os.remove(temp_path + temp_file)
            else:
                rmtree(temp_path + temp_file)

    if email_sent:
        return response_200

    else:
        return response_500


if __name__ == "__main__":
    main()
