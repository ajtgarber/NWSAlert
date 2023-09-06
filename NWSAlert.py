# pip install pillow, dotenv, discord_webhook, geopandas

import json
import requests
import time
from datetime import datetime, timedelta
import os
import io
import geopandas
from shapely.geometry import Point, Polygon
from PIL import Image
from PIL import ImageDraw
import imageio.v2 as imageio
import urllib

from dotenv import load_dotenv
from discord_webhook import DiscordWebhook, DiscordEmbed

load_dotenv()

WEBHOOK_URL = os.environ['WEBHOOK_URL']
GPS_COORDS = os.environ['GPS_COORDS']
RADAR_SITE = 'koun'

known_alerts = []

headers = {
	'User-Agent': '(Test Weather Alerting, ajtgarber@gmail.com)'
}

try:
	response = requests.get("https://api.weather.gov/points/%s"%(GPS_COORDS), headers=headers)
	if response.status_code != 200:
		print("Received server error attempting to determine radar site, using default value")
	response = json.loads(response.text)
	RADAR_SITE = response["properties"]["radarStation"]
	print("Detected radar site: %s" %  (RADAR_SITE))
except requests.exceptions.RequestException as e:
	print("Unable to determine radar site of specified coordinates, using default value")

def determine_spc_url():
    utcnow = datetime.utcnow()
    year = utcnow.year
    timestamp = ""
    outlook_time = ""
    #Convective Outlook Issuance Times
    #Day 1 Convective Outlook - 0600Z, 1300Z, 1630Z, 2000Z, and 0100Z
    if utcnow.hour >= 20:
        outlook_time = "2000"
        timestamp = utcnow.strftime("%Y%m%d_2000")
    elif utcnow.hour > 16 or (utcnow.hour == 16 and utcnow.minute >= 30):
        outlook_time = "1630"
        timestamp = utcnow.strftime("%Y%m%d_1630")
    elif utcnow.hour >= 13:
        outlook_time = "1300"
        timestamp = utcnow.strftime("%Y%m%d_1300")
    elif utcnow.hour >= 6:
        outlook_time = "0600"
        timestamp = utcnow.strftime("%Y%m%d_0600")
    elif utcnow.hour >= 1:
        outlook_time = "0100"
        timestamp = utcnow.strftime("%Y%m%d_0100")
    elif utcnow.hour == 0:
        outlook_time = "2000"
        utcnow = utcnow - timedelta(days=1)
        timestamp = utcnow.strftime("%Y%m%d_2000")
    spc_url = f"https://www.spc.noaa.gov/products/outlook/archive/{year}/day1otlk_{timestamp}_cat.lyr.geojson"
    page_title = utcnow.strftime("%b %d, %Y")+" "+outlook_time+" UTC Day 1 Convective Outlook"
    return (spc_url, page_title)

def send_alert(timestamp, title, text, image, id):
	content = "**" + title + "**\n" + text
	time.sleep(1)
	webhook = DiscordWebhook(WEBHOOK_URL, rate_limit_retry=True)
	embed = DiscordEmbed(title=title, description=text, timestamp=timestamp)
	
	embed.set_footer(text=id)
	if image is not None:
		byte_array = io.BytesIO()
		image.save(byte_array, format='PNG')
		
		webhook.add_file(file=byte_array.getvalue(), filename="warn.png")
		embed.set_image(url="attachment://warn.png")
	
	webhook.add_embed(embed)
	response = webhook.execute()

def request_alerts():
	time.sleep(1)
	response = None
	
	for counter in range(0, 5):
		try:
			#response = requests.get("https://api.weather.gov/alerts/active?point="+GPS_COORDS, headers=headers)
			#response = requests.get("https://api.weather.gov/alerts?point="+GPS_COORDS, headers=headers)
		except requests.exceptions.RequestException as e:
			print("Caught RequestException from server")
			print(e)
			time.sleep(10)
			continue
		if response.status_code != 200:
			print("Received an error from the server, assuming we've hit the rate-limit")
			print(str(response.status_code))
			time.sleep(90)
		else:
			break
	
	if response.status_code != 200:
		print("We have retried 5 times, something's wrong")
		return None

	try:
		messages = json.loads(response.text)
	except json.JSONDecodeError:
		print("Unable to decode JSON response")
		return None

	if "features" not in messages:
		print("We weren't able to find features within messages dict")
		send_alert(datetime.now().strftime("%m/%d/%Y %h:%M"), "Features not found", "Features not found within messages dict", None)
		return None
	warnings = messages["features"]
	return warnings
	
def pull_image(image_url):
        try:
                image_request = requests.get(image_url)
        except requests.exceptions.RequestException as e:
                print("Received RequestException while trying to get image data")
                print(e)
                return None
        if image_request.status_code != 200:
                print("Received an internal server error")
                return None
        image_bytes = io.BytesIO(image_request.content)
        try:
                image = Image.open(image_bytes)
        except PIL.UnidentifiedImageError:
                print("Unable to parse image data from NOAA")
                return None
       	return image

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
	
	old_range_x = abs(max_x - min_x)
	old_range_y = abs(max_y - min_y)
	new_range_x = 2000
	new_range_y = 2000
	transformed_polygon = []
	for point in warning_polygon:
		new_x = (((point[0] - min_x) * new_range_x) / old_range_x)
		new_y = (((point[1] - min_y) * new_range_y) / old_range_y)
		transformed_polygon.append(new_x)
		transformed_polygon.append(new_range_y - new_y)
	
	bbox = str(min_x)+","+str(min_y)+","+str(max_x)+","+str(max_y)
	reflectivity_url = "https://opengeo.ncep.noaa.gov/geoserver/"+RADAR_SITE+"/ows?service=wms&version=1.3.0&request=GetMap&format=image/jpeg&LAYERS="+RADAR_SITE+"_bref_raw&WIDTH=2000&HEIGHT=2000&BBOX="+bbox
	reflectivity = pull_image(reflectivity_url)
	if reflectivity is None:
		return None
	draw = ImageDraw.Draw(reflectivity, 'RGBA')
	draw.polygon(transformed_polygon, fill=(255, 0, 0, 125), outline=(255, 0, 0, 125))
	
	velocity_url = "https://opengeo.ncep.noaa.gov/geoserver/"+RADAR_SITE+"/ows?service=wms&version=1.3.0&request=GetMap&format=image/jpeg&LAYERS="+RADAR_SITE+"_bvel_raw&WIDTH=2000&HEIGHT=2000&BBOX="+bbox
	velocity = pull_image(velocity_url)
	if velocity is None:
		return None
	draw = ImageDraw.Draw(velocity, 'RGBA')
	draw.polygon(transformed_polygon, fill=(255, 0, 0, 125), outline="red")
	
	final = Image.new('RGB', (reflectivity.width, reflectivity.height+velocity.height))
	final.paste(reflectivity, (0,0))
	final.paste(velocity, (0, reflectivity.height))

	return final

last_spc_url = ""
while True:	
	spc_url, spc_title = determine_spc_url()
	if spc_url != last_spc_url:
		last_spc_url = spc_url
		print(spc_url)
		day1_outlook = None
		try:
			day1_outlook = geopandas.read_file(spc_url)
		except urllib.error.HTTPError as e:
			print("Received error while trying to retreieve outlook, we may have gotten here too early")
			last_spc_url = ""

		if day1_outlook is not None:
			geom = day1_outlook['geometry']
			labels = day1_outlook['LABEL']

			home_str = GPS_COORDS.split(",")
			lat = home_str[0]
			long = home_str[1]
			home = Point(long, lat)

			alert_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.00Z")
			risk = home.within(geom)
			severe_risk = False
			risk_types = {
				"TSTM" : "Thunderstorm",
				"MRGL" : "Marginal",
				"SLGT" : "Slight",
				"ENH"  : "Enhanced",
				"MDT"  : "Moderate",
				"HIGH" : "High",
				"None" : "None"
			}
			risk_type = "None"
			for index, row in risk.items():
				if row == True:
					severe_risk = True
					risk_type = labels[index]
			risk_type = risk_types[risk_type]
			if severe_risk:
				print("[" + str(datetime.now()) + "] You are subject to a "+risk_type+" severe risk today.")
				outlook_image = Image.open(requests.get("https://www.spc.noaa.gov/products/outlook/day1otlk.gif", stream=True).raw)
				send_alert(alert_time, "Your area is subject to a " + risk_type + " severe risk today", spc_title, outlook_image, "https://www.spc.noaa.gov/products/outlook/day1otlk.gif")

	warnings = request_alerts()
	if warnings != None:
		print("[" + str(datetime.now()) + "] NWS is reporting " + str(len(warnings)) + " alerts for your area")
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
			
			event = message["properties"]["event"]
			description = message["properties"]["description"]
			id = message["properties"]["@id"]

			initial_description = ""
			hazard_line = ""
			source_line = ""
			impact_line = ""
			
			if "HAZARD" in description:
				initial_description = description[ : description.index("HAZARD")].replace("\n", " ").strip()
				hazard_line = description[description.index("HAZARD") : description.index("SOURCE")].strip()
				source_line = description[description.index("SOURCE") : description.index("IMPACT")].strip()
				impact_line = description[description.index("IMPACT") : description.index("Locations impacted")].replace("\n", " ").strip()
			elif "WHAT" in description: #doesn't totally align with variables, but will clean up later
				initial_description = description[description.index("WHAT...") : description.index("WHERE...")].replace("\n", " ").strip()
				hazard_line = description[description.index("WHERE...") : description.index("WHEN...")].strip()
				source_line = description[description.index("WHEN...") : description.index("IMPACTS...")].strip()
				impact_line = description[description.index("IMPACTS...") : ].strip()
			elif "Special Weather" in event or "Alert" in event:
				initial_description = description

			print("Initial: " + initial_description)
			print("Hazard: " + hazard_line)
			print("Source: " + source_line)
			print("Impact: " + impact_line)
			
			warning_polygon = None
			warning_image = None
			if "geometry" in message and message["geometry"] is not None:
				warning_polygon = message["geometry"]["coordinates"][0]
				warning_image = generate_warning_image(warning_polygon)
				#warning_image.show()
			
			print("------")
			print()
			body = "" + initial_description + "\n\n" + hazard_line + "\n" + source_line + "\n" + impact_line
			send_alert(message["properties"]["effective"], message["properties"]["headline"], body, warning_image, id)
	else:
		print("We were unable to successfully request information from the server")
		break
	time.sleep(300)
