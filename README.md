# EU exchange rates service

This application retrieves current exchange rates from the European Central Bank's SDMX API and sends them to an e-mail in Excel spreadsheet. If today's exchange rates are not yet available, the ones from the last workday will be returned.

You can deploy it to Google Cloud Run or run it locally.

## Basic configuration

Firstly you need to edit the config.json file, which contains the following parameters:
- `target_email_address`: E-mail address the report will be sent to
- `sender_email_address`: E-mail address the report will be sent from
- `sender_email_smtp_address`: Sender's SMTP address
- `sender_email_smtp_port`: Sender's SMTP port
- `use_locally`: `true` when running the application locally, `false` when deploying on cloud
- `currencies`: list of currencies that you are interested in (e.g. CZK, HUF); by default this is filled with all EU currencies

## Google Cloud configuration
In any case, you need to enable Google Cloud Secret Manager and Cloud Logging. To deploy the application to GCP, you also need to enable Cloud Run and Artifact Registry.

Password for the sender's e-mail should be stored in Secret Manager under the name `email_password` and the service account under which the service is deployed needs to have the Secret Manager Secret Accessor permission.

All application logs will be sent to Cloud Logging.

## Local use

1. Use the package manager [pip](https://pip.pypa.io/en/stable/) to install requirements.

```bash
pip install -r requirements.txt
```
2. Set parameter `use_locally` in `config.json` to `true`.
3. Export a JSON file with service account credentials from GCP. Put it in the main directory and name it `service_account.json`.
4. Run:
```bash
python main.py
```

## Cloud use
1. Set parameter `use_locally` in `config.json` to `false`.

2. Build docker image:

```python
docker build .
```
3. Push the image to Artifact Registry and use it to create the Cloud Run service. More information about pushing to Artifact registry can be found [here](https://cloud.google.com/artifact-registry/docs/docker/store-docker-container-images). Do not include `service_account.json` in the image - credentials will be determined automatically.
4. Invoke the service with a POST HTTP request (use Cloud Scheduler to do it periodically).


## Resources

[SDMX API](https://sdw-wsrest.ecb.europa.eu/help/)