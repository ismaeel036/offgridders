"""
Following excample:
https://github.com/oemof/oemof_examples/blob/master/examples/oemof_0.2/basic_example/basic_example.py#L84

Energy system modeled: Micro Grid with fixed capacities

            input/output    bus_fuel        bus_electricity     flow
                    |               |               |
                    |               |               |
source: pv          |------------------------------>|       generate_pv (fix)
                    |               |               |
source: fossil_fuel |-------------->|               |       fossil_fuel_in (var)
                    |               |               |
trafo: generator    |<--------------|               |       fossil_fuel_use (var)
                    |------------------------------>|       generate_fuel (var)
                    |               |               |
storage: battery    |<------------------------------|       battery_charge (var)
                    |------------------------------>|       battery_discharge (var)
                    |               |               |
sink: demand        |<------------------------------|       supply_demand (fix)
                    |               |               |
sink: excess        |<------------------------------|       supply_excess (var)
                    |               |               |

_____
Data used: None

_________
Requires:
oemof, matplotlib, demandlib, pvlib
tables, tkinter

"""

###############################################################################
# Imports and initialize
###############################################################################

from oemof.tools import logger
# from oemof.tools import helpers

import oemof.solph as solph
import oemof.outputlib as outputlib

import logging
# Logging
logger.define_logging(logfile='energy_system_main.log',
                      screen_level=logging.INFO,
                      file_level=logging.DEBUG)

import os
import pandas as pd
import pprint as pp

# Try to import matplotlib librar
try:
    import matplotlib.pyplot as plt
except ImportError:
    logging.info('Attention! matplotlib could not be imported.')
    plt = None

# import own functions
from demand_profile import demand_profile
from pvlib_scripts import pvlib_scripts

###############################################################################
# Simulation settings
###############################################################################

# Import general simulation settings
from config import solver, solver_verbose, debug
# File structure
from config import output_folder, output_file
# Import specific simulation settings
from config import display_graphs, date_time_index
###############################################################################
# Input values
###############################################################################
# demand
from input_values import demand_input
# costs
from input_values import cost_data, fuel_price
# fixed capacities
from input_values import cap_fuel_gen, cap_pv, cap_storage
# pv system
from input_values import pv_system_location, location_name, pv_system_parameters, pv_composite_name

# Estimate Load profile
# todo check for units
demand_profile = demand_profile.estimate(demand_input) # wh? kWh?

# Solar irradiance
# todo check for units
solpos, dni_extra, airmass, pressure, am_abs, tl, cs = pvlib_scripts.irradiation(pv_system_location, location_name)

# PV generation
# todo check for units
pv_generation_per_panel = pvlib_scripts.generation(pv_system_parameters, pv_composite_name, location_name, solpos, dni_extra, airmass, pressure, am_abs, tl, cs)

###############################################################################
# Initialize Energy System
###############################################################################

logging.info('Initialize the energy system')

# create energy system
micro_grid_system = solph.EnergySystem(timeindex=date_time_index)

###############################################################################
# Create Energy System with oemof
###############################################################################

logging.info('Create oemof objects for Micro Grid System (off-grid, fixed capacities)')

# create AC electricity bus of distribution grid
bus_electricity_mg = solph.Bus(label="bus_electricity_mg")

# create fuel bus
bus_fuel = solph.Bus(label="bus_fuel")

# add bus_electricity_mg and bus_fuel to micro_grid_system
micro_grid_system.add(bus_electricity_mg, bus_fuel)

# create and add fuel source to micro_grid_system - variable
source_fuel=solph.Source(label="source_fuel",
             outputs={bus_fuel: solph.Flow(variable_costs=fuel_price)}  #  ??
            )

# create and add pv generation source to micro_grid_system - fixed
source_pv=solph.Source(label="source_pv",
             outputs={bus_electricity_mg: solph.Flow(label='PV generation',
                 actual_value=pv_generation_per_panel,
                 fixed=True,
                 nominal_value=cap_pv
                 #investment=solph.Investment(ep_costs=cost_data.loc['annuity', 'PV'])
                 )}
             )

# create and add demand sink to micro_grid_system - fixed
sink_demand=solph.Sink(label="sink_demand",
           inputs={bus_electricity_mg: solph.Flow(
               actual_value=demand_profile,
               nominal_value=1,
               fixed=True)}
           )

# create and add excess electricity sink to micro_grid_system - variable
sink_excess=solph.Sink(label="sink_excess",
           inputs={bus_electricity_mg: solph.Flow()}
           )

# create and add fuel generator (transformer) to micro_grid_system - variable
transformer_fuel_generator=solph.Transformer(label="transformer_fuel_generator",
                  inputs={bus_fuel: solph.Flow()},
                  outputs={bus_electricity_mg: solph.Flow(
                      nominal_value=cap_fuel_gen,
                      variable_costs=50)},
                  #investment=solph.Investment(ep_costs=cost_data.loc['annuity', 'GenSet']),
                  conversion_factors={bus_electricity_mg: 0.58}  # is efficiency of the generator?? Then this should later on be included as a function of the load factor
                  )

# create and add storage object representing a battery - variable
generic_storage = solph.components.GenericStorage(
    label='generic_storage',
    nominal_capacity=cap_storage,
    #investment=solph.Investment(ep_costs=cost_data.loc['annuity', 'Storage']),
    inputs={bus_electricity_mg: solph.Flow(
        nominal_value=cap_storage/6)},  # 10077997/6 is probably the maximum charge/discharge possible in one timestep
    outputs={bus_electricity_mg: solph.Flow(
        nominal_value=cap_storage/6,
        variable_costs=0.0)},
    capacity_loss=0.00,  # from timestep to timestep? what is this?
    initial_capacity=None,  # in terms of SOC?
    inflow_conversion_factor=1,  # storing efficiency?
    outflow_conversion_factor=0.8  # efficiency of feed-in-stored?
)

micro_grid_system.add(sink_demand, sink_excess, source_fuel, source_pv, transformer_fuel_generator, generic_storage)

###############################################################################
# Optimise the energy system and plot the results
###############################################################################

logging.info('Optimise the energy system of the micro grid')

# initialise the operational model
model = solph.Model(micro_grid_system)

# if tee_switch is true solver messages will be displayed
logging.info('Solve the optimization problem')
model.solve(solver=solver, solve_kwargs={'tee': solver_verbose})

logging.info('Store the energy system with the results.')

# The processing module of the outputlib can be used to extract the results
# from the model transfer them into a homogeneous structured dictionary.

# add results to the energy system to make it possible to store them.
micro_grid_system.results['main'] = outputlib.processing.results(model)
micro_grid_system.results['meta'] = outputlib.processing.meta_results(model)

#todo Enter check for directory and create directory here!
# store energy system with results
micro_grid_system.dump(dpath=output_folder, filename=output_file)

# ****************************************************************************
# ********** PART 2 - Processing the results *********************************
# ****************************************************************************

logging.info('**** The script can be divided into two parts here.')
logging.info('Restore the energy system and the results.')
micro_grid_system = solph.EnergySystem()

micro_grid_system.restore(dpath=output_folder, filename=output_file)

# define an alias for shorter calls below (optional)
results = micro_grid_system.results['main']
storage = micro_grid_system.groups['generic_storage']

# print a time slice of the state of charge
print('')
print('********* State of Charge (slice) *********')
print(results[(storage, None)]['sequences']['2018-02-25 08:00:00':
                                            '2018-02-26 15:00:00'])
print('')

# get all variables of a specific component/bus
custom_storage = outputlib.views.node(results, 'generic_storage')
electricity_bus = outputlib.views.node(results, 'bus_electricity_mg')

# plot the time series (sequences) of a specific component/bus
#todo plots not working
if plt is not None:
    logging.info('Plotting: Generic storage')
    custom_storage['sequences'].plot(kind='line', drawstyle='steps-post')
    plt.show()
    logging.info('Plotting: Electricity bus')
    electricity_bus['sequences'].plot(kind='line', drawstyle='steps-post')
    plt.show()

# print the solver results
print('********* Meta results *********')
pp.pprint(micro_grid_system.results['meta'])
print('')

# print the sums of the flows around the electricity bus
print('********* Main results *********')
print(electricity_bus['sequences'].sum(axis=0))

'''
results = outputlib.processing.results(model)

custom_storage = outputlib.views.node(results, 'generic_storage')
electricity_bus = outputlib.views.node(results, 'bus_electricity_mg')

print (electricity_bus)

if plt is not None:
    logging.info('Plotting: Generic storage')
    custom_storage['sequences'].plot(kind='line', drawstyle='steps-post')
    plt.show()
    logging.info('Plotting: Electricity bus')
    electricity_bus['sequences'].plot(kind='line', drawstyle='steps-post')
    plt.show()

my_results = electricity_bus['scalars']

print (my_results)
print(results[(generic_storage, None)])

# installed capacity of storage in GWh
my_results['storage_invest_kWh'] = (results[(generic_storage, None)]
                                    ['scalars']['invest'])

# installed capacity of pv power plant in MW
my_results['pv_invest_kW'] = (results[(source_pv, bus_electricity_mg)]
                              ['scalars']['invest'])

# resulting renewable energy share
my_results['res_share'] = (1 - results[(transformer_fuel_generator, bus_electricity_mg)]
                           ['sequences'].sum()/results[(bus_electricity_mg, sink_demand)]
['sequences'].sum())
'''