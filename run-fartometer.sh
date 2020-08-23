#!/bin/sh

cd /home/pi/sdk-cpp-workspace/fartometer
/usr/bin/python sense_main.py --endpoint "a5r16h71o6euo-ats.iot.us-west-2.amazonaws.com" --cert /home/pi/AWS_Certs/9edb4854f4-certificate.pem.crt --key /home/pi/AWS_Certs/9edb4854f4-private.pem.key --root-ca /home/pi/AWS_Certs/AmazonRootCA1.pem --client-id "arn:aws:iot:us-west-2:580778568985:thing/HomePi3A"

