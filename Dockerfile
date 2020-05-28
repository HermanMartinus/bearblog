FROM python:3.6.5
ENV DEBUG=False
ENV SECRET=passsomesecret
ENV SENDGRID_API_KEY=passsomeapikey
WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . /app/
COPY docker-entrypoint.sh /usr/local/bin/
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
