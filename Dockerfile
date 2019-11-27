FROM python:3
ADD App.py /
ADD .env /
ADD requirements.txt /
RUN pip install -r requirements.txt
RUN mkdir -p /mnt/in
RUN mkdir -p /mnt/out
RUN mkdir -p /mnt/outer
CMD ["python","./App.py"]
