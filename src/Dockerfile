# 
FROM python:3.9-alpine

# 
WORKDIR /src

# 
COPY ./requirements.txt /src/requirements.txt

# 
RUN pip install -r /src/requirements.txt

# 
COPY . /src

# 
ENTRYPOINT ["uvicorn", "--host", "0.0.0.0", "--port", "80"]