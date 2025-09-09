room_lists = [
    {"id": 1, "name": "201", "room_type": "Single", "equipments": ["TV monitor", "Bathroom", "Sofa", "Refrigerator", "Bed"]},
    {"id": 2, "name": "202", "room_type": "Single", "equipments": ["TV monitor", "Bathroom", "Sofa", "Refrigerator", "Bed"]},
    {"id": 3, "name": "203", "room_type": "Single", "equipments": ["TV monitor", "Bathroom", "Sofa", "Refrigerator"]},
    {"id": 4, "name": "204", "room_type": "Single", "equipments": ["TV monitor", "Bathroom", "Sofa", "Refrigerator", "Bed"]},
    {"id": 5, "name": "205", "room_type": "Double", "equipments": ["TV monitor", "Bathroom", "Sofa", "Refrigerator"]},
    {"id": 6, "name": "206", "room_type": "Double", "equipments": ["TV monitor", "Bathroom", "Sofa", "Refrigerator", "Bed"]},
    {"id": 7, "name": "207", "room_type": "Suite", "equipments": ["TV monitor", "Bathroom", "Sofa"]},
    {"id": 8, "name": "208", "room_type": "Suite", "equipments": ["TV monitor", "Bathroom", "Sofa", "Refrigerator", "Bed"]},
    {"id": 9, "name": "209", "room_type": "Suite", "equipments": ["TV monitor", "Bathroom", "Sofa", "Refrigerator"]},
    {"id": 10, "name": "210", "room_type": "Suite", "equipments": ["TV monitor", "Bathroom", "Sofa", "Refrigerator", "Bed"]},
    {"id": 11, "name": "301", "room_type": "Accessible", "equipments": ["TV monitor", "Bathroom", "Sofa", "Refrigerator"]},
    {"id": 12, "name": "302", "room_type": "Accessible", "equipments": ["TV monitor", "Bathroom", "Sofa", "Refrigerator", "Bed"]},
    {"id": 13, "name": "303", "room_type": "Single", "equipments": ["TV monitor", "Bathroom", "Sofa"]},
    {"id": 14, "name": "304", "room_type": "Single", "equipments": ["TV monitor", "Bathroom", "Sofa", "Refrigerator", "Bed"]},
    {"id": 15, "name": "305", "room_type": "Double", "equipments": ["TV monitor", "Bathroom", "Sofa", "Refrigerator"]},
    {"id": 16, "name": "306", "room_type": "Double", "equipments": ["TV monitor", "Bathroom", "Sofa", "Refrigerator", "Bed"]},
    {"id": 17, "name": "307", "room_type": "Double", "equipments": ["TV monitor", "Bathroom", "Sofa"]},
    {"id": 18, "name": "308", "room_type": "Suite", "equipments": ["TV monitor", "Bathroom", "Sofa", "Refrigerator", "Bed"]},
    {"id": 19, "name": "309", "room_type": "Suite", "equipments": ["TV monitor", "Bathroom", "Sofa", "Refrigerator"]},
    {"id": 20, "name": "310", "room_type": "Accessible", "equipments": ["TV monitor", "Bathroom", "Sofa", "Refrigerator", "Bed"]}
]

bookings = [

]

from flask import Flask, render_template, request, redirect, url_for, jsonify
from datetime import date
import dateparser


app = Flask(__name__)

def is_conflict_free(startA: date, endA: date, startB: date, endB: date) -> bool:
    # Returns True if there is NO conflict (no overlap)
    return (endA < startB) or (endB < startA)

def equal_ignore_case(a, b):
    return str(a).casefold() == str(b).casefold()

@app.route('/')
def index():
    return render_template('index.html', rooms=room_lists, bookings=bookings)


@app.route('/book', methods=['POST'])
def book():
    try:
        print("I am on booking....")
        data = request.get_json()
        if not data:
            return jsonify(room_list=[], status="Invalid or missing JSON")

        full_name = data.get('full_name')
        check_in = data.get('check_in')
        check_out = data.get('check_out')
        room_number = data.get('room_number')

        print(f"Booking.. : {full_name}, {room_number}, {check_in}, {check_out}")

        bookings.append({ 
            "full_name": full_name,
            "check_in" : check_in,
            "check_out": check_out,
            "name": room_number
        })

        return jsonify(status="Ok")

    except Exception as e:
        print(f"Error occurred: {str(e)}")
        return jsonify(status=f"failure : {str(e)}")


@app.route('/lookout', methods=['POST'])
def lookout():
    try: 
        print("I am on looking out....")
        data = request.get_json()
        if not data:
            return jsonify(room_list=[], status="Invalid or missing JSON")

        room_type = data.get('room_type')
        check_in = data.get('check_in')
        check_out = data.get('check_out')

        print(f"Lookout : {room_type}, {check_in}, {check_out}")

        check_in = dateparser.parse(check_in)
        check_out = dateparser.parse(check_out)

        # all possible rooms
        possible_room_lists = [room for room in room_lists if equal_ignore_case(room['room_type'], room_type)]

        # Look out the existing booking
        for booking in bookings:
            booked_check_in = dateparser.parse(booking['check_in'])
            booked_check_out = dateparser.parse(booking['check_out'])
            
            # find out the conflict room, remove it from possible rooms
            if equal_ignore_case(booking['room_type'], room_type) and is_conflict_free(check_in, check_out, booked_check_in, booked_check_out) == False:
                possible_room_lists = [room for room in possible_room_lists if room.get("name") != booking['name']]

        # available room names
        available_room_names = [room['name'] for room in possible_room_lists]
        print(f"available_rooms : {available_room_names}")

        return jsonify(room_list= "'" + "', '".join(available_room_names) + "'", status="Ok")
    
    except Exception as e:
        print(f"Error occurred: {str(e)}")
        return jsonify(room_list=[], status=f"failure : {str(e)}")




if __name__ == '__main__':
    app.run(debug=False)