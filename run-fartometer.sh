#!/bin/sh

cd /home/pi/sdk-cpp-workspace/fartometer
while true
do
	/usr/bin/python sense_main.py --endpoint "a5r16h71o6euo-ats.iot.us-west-2.amazonaws.com" --cert "/home/pi/AWS_Certs/6de2893c32-certificate.pem.crt" --key "/home/pi/AWS_Certs/6de2893c32-private.pem.key" --client-id "arn:aws:iot:us-west-2:580778568985:thing/HomePiZero" --root-ca /home/pi/AWS_Certs/AmazonRootCA1.pem --sensor ccs811
	sleep 60
done

