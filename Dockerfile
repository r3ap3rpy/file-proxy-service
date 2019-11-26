FROM python:3
ADD App.py /
ADD .env /
ADD requirements.txt /
RUN pip install -r requirements.txt
RUN mkdir -p /in
RUN mkdir -p /out
CMD ["python","./App.py"]
EXPOSE 8080
