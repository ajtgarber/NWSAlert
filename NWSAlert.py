import json
import requests
import time
import datetime
import os
import io
from PIL import Image
from PIL import ImageDraw

from dotenv import load_dotenv

load_dotenv()

WEBHOOK_URL = os.environ['WEBHOOK_URL']
GPS_COORDS = os.environ['GPS_COORDS']
RADAR_SITE = 'ktlx'

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
		response = requests.get("https://api.weather.gov/alerts?point="+GPS_COORDS, headers=headers)
		
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
	
def generate_warning_image(warning_polygon):
	min_x =  9999
	min_y =  9999
	max_x = -9999
	max_y = -9999
	for point in warning_polygon:
		if point[0] < min_x: min_x = point[0]
		if point[0] > max_x: max_x = point[0]
		if point[1] < min_y: min_y = point[1]
		if point[1] > max_y: max_y = point[1]
	
	old_range_x = max_x - min_x
	old_range_y = max_y - min_y
	new_range_x = 2000
	new_range_y = 2000
	transformed_polygon = []
	for point in warning_polygon:
		new_x = (((point[0] - min_x) * new_range_x) / old_range_x)
		new_y = (((point[1] - min_y) * new_range_y) / old_range_y)
		transformed_polygon.append(new_x)
		transformed_polygon.append(new_y)
	
	bbox = str(min_x)+","+str(min_y)+","+str(max_x)+","+str(max_y)
	reflectivity_request = requests.get("https://opengeo.ncep.noaa.gov/geoserver/"+RADAR_SITE+"/ows?service=wms&version=1.3.0&request=GetMap&format=image/jpeg&LAYERS="+RADAR_SITE+"_bref_raw&WIDTH=2000&HEIGHT=2000&BBOX="+bbox)
	reflectivity_bytes = io.BytesIO(reflectivity_request.content)
	reflectivity = Image.open(reflectivity_bytes)
	ref2 = reflectivity.copy()
	draw = ImageDraw.Draw(ref2)
	draw.polygon(transformed_polygon, fill="red", outline="red")
	ref3 = Image.blend(reflectivity, ref2, 0.5)
	return ref3

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
			
			initial_description = ""
			hazard_line = ""
			source_line = ""
			impact_line = ""
			
			if "HAZARD" in description:
				initial_description = description[ : description.index("HAZARD")].replace("\n", " ").strip()
				hazard_line = description[description.index("HAZARD") : description.index("SOURCE")].strip()
				source_line = description[description.index("SOURCE") : description.index("IMPACT")].strip()
				impact_line = description[description.index("IMPACT") : description.index("Locations impacted")].replace("\n", " ").strip()
			
			print("Initial: " + initial_description)
			print("Hazard: " + hazard_line)
			print("Source: " + source_line)
			print("Impact: " + impact_line)
			
			warning_polygon = message["geometry"]["coordinates"][0]
			warning_image = generate_warning_image(warning_polygon)
			warning_image.show()
			
			print("------")
			print()
			body = "" + initial_description + "\n\n" + hazard_line + "\n" + source_line + "\n" + impact_line
			send_alert(message["properties"]["effective"], message["properties"]["headline"], body)
	else:
		print("We were unable to successfully request information from the server")
		break
	time.sleep(45)
