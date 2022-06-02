import json
import requests
import time
import datetime
import os

from dotenv import load_dotenv

load_dotenv()

WEBHOOK_URL = os.environ['WEBHOOK_URL']
GPS_COORDS = os.environ['GPS_COORDS']

known_alerts = []

def send_alert(timestamp, title, text):
	content = "**" + title + "**\n" + text
	#data = {
	#	"content" : content,
	#	"username" : "WXAlert"
	#}
	data = {
		"embeds": [{
			"title" : title,
			"description" : text,
			"timestamp" : timestamp#,
			#"image" : {
			#	"url" : "https://radar.weather.gov/ridge/lite/KILN_loop.gif"
			#}
		}]
	}
	
	result = requests.post(WEBHOOK_URL, json = data)

def request_alerts():
	headers = {
		'User-Agent': '(Test Weather Alerting, ajtgarber@gmail.com)'
	}
	time.sleep(1)
	response = None
	
	for counter in range(0, 5):
		response = requests.get("https://api.weather.gov/alerts/active?point="+GPS_COORDS, headers=headers)
		
		if response.status_code != 200:
			print("Received an error from the server, assuming we've hit the rate-limit")
			time.sleep(10)
		else:
			break
	
	if response.status_code != 200:
		print("We have retried 5 times, something's wrong")
		return None

	messages = json.loads(response.text)

	warnings = messages["features"]
	return warnings

while True:	
	warnings = request_alerts()
	if warnings != None:
		print("[" + str(datetime.datetime.now()) + "] NWS is reporting " + str(len(warnings)) + " alerts for your area")
		for message in warnings:
			if message["properties"]["@id"] in known_alerts:
				print("We already know about alert ID: " + message["properties"]["@id"])
				continue
			
			print("------")
			print(message["properties"]["@id"])
			print(message["properties"]["headline"])
			print("MessageType " + message["properties"]["messageType"])
			print("Issued " + message["properties"]["effective"])
			print("Ends " + str(message["properties"]["ends"]))
			
			known_alerts.append(message["properties"]["@id"])
			
			description = message["properties"]["description"]		
			initial_description = description[ : description.index("HAZARD")].replace("\n", " ").strip()
			hazard_line = description[description.index("HAZARD") : description.index("SOURCE")].strip()
			source_line = description[description.index("SOURCE") : description.index("IMPACT")].strip()
			impact_line = description[description.index("IMPACT") : description.index("Locations impacted")].replace("\n", " ").strip()
			
			print("Initial: " + initial_description)
			print("Hazard: " + hazard_line)
			print("Source: " + source_line)
			print("Impact: " + impact_line)
			
			print("------")
			print()
			body = "" + initial_description + "\n\n" + hazard_line + "\n" + source_line + "\n" + impact_line
			send_alert(message["properties"]["effective"], message["properties"]["headline"], body)
	else:
		print("We were unable to successfully request information from the server")
		break
	time.sleep(45)
