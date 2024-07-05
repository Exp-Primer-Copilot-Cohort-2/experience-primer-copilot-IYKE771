import math
import gurobipy as gp
from gurobipy import GRB

# Parameters
I_avg = 4.5  # kWh/m²/day
Q_demand = 5  # kWh/day
rho_water = 1000  # kg/m³
C_p_water = 4.18 / 3600  # kWh/kg/K
T_initial = 22  # °C
T_final = 70  # °C
tilted_angle = 21.6  # degrees
V_tank = 70  # m³
heating_time = 40 / 60  # 40 minutes converted to hours

# Material properties and costs
thermal_conductivity_copper = 1200  # W/mK   ####I have restricted it not to influence the energy
cost_copper_pipe = 220  # GHS per pipe
cost_galvanized_steel_plate = 360  # GHS
cost_fiberglass = 300  # GHS
cost_galvanized_steel_tank = 350  # GHS
cost_wood = 50  # GHS per m² of wood
thermal_conductivity_steel = 50  # W/mK  ###I have restricted it not to influence the energy

# Thickness and diameter of materials (mm)
thickness_copper_pipe = 2  # mm
diameter_copper_pipe = 0.0113  # mm
thickness_insulated_collector = 0.04  # m (40 mm for hard foam)
thickness_insulated_tank = 0.02  # m (20 mm for fiberglass)
thickness_galvanized_steel_plate = 1  # mm
thickness_galvanized_steel_tank = 2  # mm

# Convert specific heat capacity to kWh/kg/K
C_p_water /= 3600  # kWh/kg/K

# Hourly irradiance (7 hours of sun)
hourly_irradiance = I_avg / 7  # kWh/m²/h
hours = list(range(7))  # Sunshine hours from 6 AM to 1 PM

# Shadowing model (adjust as needed)
def shadow_factor(time_of_day):
    if 10 <= time_of_day <= 14:
        return 0.70
    else:
        return 1

# Calculate shadow-adjusted irradiance considering tilted angle
def adjusted_irradiance(hourly_irradiance, sunshine_hours, tilted_angle):
    adjusted = []
    for hour in sunshine_hours:
        time_of_day = hour + 7
        angle_factor = math.cos(math.radians(tilted_angle))
        adjusted.append(hourly_irradiance * shadow_factor(time_of_day) * angle_factor)
    return adjusted

# Function to calculate heat loss
def calculate_heat_loss(thickness_insulation, T_initial, T_final):
    return 0.1 * thickness_insulation * (T_final - T_initial)

# Function to run optimization
def run_optimization():
    # Calculate adjusted hourly irradiance
    I_hourly_adjusted = adjusted_irradiance(hourly_irradiance, hours, tilted_angle)
    total_adjusted_irradiance = sum(I_hourly_adjusted)

    # Model setup
    m = gp.Model("thermosyphon_water_heating")

    # Variables
    A_collector = m.addVar(vtype=GRB.INTEGER, lb=2, name="A_collector")  # Area of the collector (m²)### I have restricted it not to influence the energy
    N_pipes = m.addVar(vtype=GRB.INTEGER, lb=12, name="N_pipes")  # Number of copper pipes  #### I have restricted it not to influence the energy
    C = m.addVar(lb=0, name="Total_Cost")  # Total cost (GHS)
    L_pipes = m.addVar(name="Total_Length_of_Pipes")  # Total length of copper pipes (m)

    # Tank insulation variables
    thickness_insulation_tank = m.addVar(lb=0.01, ub=0.6, name="Thickness_Insulation_Tank") ### I have restricted it not to influence the energy
    # Collector insulation variables
    thickness_insulation_collector = m.addVar(lb=0.01, ub=0.5, name="Thickness_Insulation_Collector")###I have restricted it not to influence the energy

    # Binary variable for insulation material
    is_hard_foam_collector = m.addVar(vtype=GRB.BINARY, name="Is_Hard_Foam_Collector")  # 1 if hard foam, 0 otherwise
    is_fiberglass_tank = m.addVar(vtype=GRB.BINARY, name="Is_Fiberglass_Tank")  # 1 if fiberglass, 0 otherwise

    # Calculate required energy to heat water to desired temperature within the heating time
    delta_T = T_final - T_initial  # Temperature change (°C)
    energy_required_per_batch = rho_water * V_tank * C_p_water * delta_T / heating_time  # kWh

    # Objective function: minimize total cost
    m.setObjective(C, GRB.MINIMIZE)

    # Constraints
    # Adjust total energy absorbed calculation to include thermal conductivity of steel plate and copper pipes
    R_steel = thickness_galvanized_steel_plate / 1000 / thermal_conductivity_steel  # Thermal resistance (m²K/W)
    R_copper = (thickness_copper_pipe / 1000) / (thermal_conductivity_copper * (math.pi * (diameter_copper_pipe / 1000)))  # Thermal resistance (m²K/W)
    effective_energy_absorbed = gp.quicksum(I_hourly_adjusted[hour] * A_collector for hour in hours)
    m.addConstr(effective_energy_absorbed * (1 /(R_steel + R_copper)) >= energy_required_per_batch + calculate_heat_loss(thickness_insulated_collector, T_initial, T_final), name="Energy_Absorption")

    # Cost calculation
    m.addConstr(C == N_pipes * cost_copper_pipe + cost_galvanized_steel_plate + cost_fiberglass + cost_wood, name="Cost_Calculation")

    # Total length of pipes constraint
    m.addConstr(L_pipes == N_pipes * 3, name="Total_Length_of_Pipes")

    # Thermal conductivity of copper pipes constraint
    m.addConstr(N_pipes * thickness_copper_pipe / 1000 * A_collector * thermal_conductivity_copper >= energy_required_per_batch * (1 + 0.1), name="Thermal_Conductivity_Copper")

    # Insulation effectiveness constraints
    m.addConstr(thickness_insulation_tank * (1 - is_fiberglass_tank) >= 0.02, "Insulation_Effectiveness_Tank")
    m.addConstr(thickness_insulation_collector * is_hard_foam_collector >= 0.04, "Insulation_Effectiveness_Collector")

    # Solve model
    m.optimize()

    # Output results
    results = {}
    if m.status == GRB.OPTIMAL:
        results["energy_absorbed"] = energy_required_per_batch / total_adjusted_irradiance
        results["area_collector"] = A_collector.x
        results["total_cost"] = C.x
        results["num_pipes"] = N_pipes.x
        results["thickness_insulation_tank"] = thickness_insulation_tank.x
        results["thickness_insulation_collector"] = thickness_insulation_collector.x
        results["total_length_pipes"] = L_pipes.x
    else:
        print("No optimal solution found.")

    return results

# Run the optimization and get the results
results = run_optimization()

# Display results
if results.get("energy_absorbed") is not None:
    print("Optimal Solution Found:")
    print(f"Energy Absorbed: {results['energy_absorbed']} kWh")
    print(f"Collector Area: {results['area_collector']} m²")
    print(f"Total Cost: {results['total_cost']} GHS")
    print(f"Number of Copper Pipes: {results['num_pipes']}")
    print(f"Thickness of Tank Insulation: {results['thickness_insulation_tank']} m")
    print(f"Thickness of Collector Insulation: {results['thickness_insulation_collector']} m")
    print(f"Total Length of Copper Pipes: {results['total_length_pipes']} m")
else:
    print("No optimal solution found.")
