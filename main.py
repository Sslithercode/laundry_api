from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware  # Import the CORS middleware
from pydantic import BaseModel
import threading
import supabase, os
import time
import json
from dotenv import load_dotenv



load_dotenv('.env')
url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_ANON_KEY")


# Timer class to handle timing functionality
class Timer:
    def __init__(self, minutes, callback=None):
        self.duration = minutes * 60
        self.start_time = None
        self.end_time = None
        self.callback = callback
        self.thread = None
    
    def start(self):
        self.thread = threading.Thread(target=self._run_timer)
        self.thread.start()

    def _run_timer(self):
        self.start_time = time.time()
        self.end_time = self.start_time + self.duration

        while time.time() < self.end_time:
            time.sleep(1)

        if self.callback:
            self.callback()

# LaundryMachine class representing each laundry machine
class LaundryMachine:
    def __init__(self, machine_type, name, serial_number):
        if machine_type not in ["washer", "dryer"]:
            raise ValueError("machine_type must be 'washer' or 'dryer'")

        self.machine_type = machine_type
        self.name = name
        self.serial_number = serial_number
        self.occupied = False
        self.time_remaining = 0
        self.timer = None

    def start_wash(self, minutes):
        if self.occupied:
            return False

        self.occupied = True
        self.time_remaining = minutes
        self.timer = Timer(minutes, self._finish_wash)
        self.timer.start()
        return True
    

    def _in_use(self):
        return "in_use" if self.occupied else "available"
    def _finish_wash(self):
        self.occupied = False
        self.time_remaining = 0

    def status(self):
        if self.occupied:
            time_passed = time.time() - self.timer.start_time
            time_left = max(0, int(self.timer.duration - time_passed))
            minutes_remaining = time_left // 60
            seconds_remaining = time_left % 60
            return {
                "name": self.name,
                "type": self.machine_type,
                "serial_number": self.serial_number,
                "status": "in_use",
                "time_remaining": f"{minutes_remaining:02}:{seconds_remaining:02}"
            }
        else:
            return {
                "name": self.name,
                "type": self.machine_type,
                "serial_number": self.serial_number,
                "status": "available",
                "time_remaining": 0
            }

# FastAPI application instance
app = FastAPI()
supabase = supabase.create_client(url, key)

# Add CORS middleware
origins = [
    "http://localhost:3000",  # Example origin
    "https://laundryprogress.vercel.app"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Allows all origins if set to ['*']
    allow_credentials=True,
    allow_methods=["*"],  # Allows all HTTP methods
    allow_headers=["*"],  # Allows all headers
)

# In-memory storage for laundry machines
machines = {}
machines_supabase = supabase.from_("laundry_machines").select("*").execute().data
# Request model for starting a wash
class StartWashRequest(BaseModel):
    minutes: int

# Function to load machines from JSON file
def load_machines_from_supabase(machines_sup):
    for machine in machines_sup:
        machine_type = machine['type']
        name = machine['name']
        serial_number = machine['serial_number']
        machines[serial_number] = LaundryMachine(machine_type, name, serial_number)

# Load machines when the application starts
load_machines_from_supabase(machines_supabase)

# Endpoint to start a wash
@app.post("/machines/{serial_number}/start_wash", response_model=dict)
def start_wash(serial_number: int, request: StartWashRequest):
    if serial_number not in machines:
        raise HTTPException(status_code=404, detail="Machine not found.")
    
    machine = machines[serial_number]
    if not machine.start_wash(request.minutes):
        raise HTTPException(status_code=400, detail="Machine is already occupied.")
    
    return {"message": f"{machine.name} has started washing for {request.minutes} minute(s)."}

# Endpoint to get the status of a laundry machine
@app.get("/machines/{serial_number}/status", response_model=dict)
def get_machine_status(serial_number: int):
    if serial_number not in machines:
        raise HTTPException(status_code=404, detail="Machine not found.")
    
    return machines[serial_number].status()


@app.get('machines/{serial_number}/reset', response_model=dict)
def reset_machine(serial_number: int):
    if serial_number not in machines:
        raise HTTPException(status_code=404, detail="Machine not found.")

    machine = machines[serial_number]
    if machine.occupied:
        raise HTTPException(status_code=400, detail="Machine is currently in use. Cannot reset.")

    machine.occupied = False
    machine.time_remaining = 0
    return {"message": f"{machine.name} has been reset."}


@app.get('machines/reset_all', response_model=dict)
def reset_all_machines():
    for machine in machines.values():
        machine.occupied = False
        machine.time_remaining = 0
    return {"message": "All machines have been reset."}


# Endpoint to get the status of all laundry machines
@app.get("/machines/all", response_model=list)
def get_all_machines_status():
    return [machine.status() for machine in machines.values()]
