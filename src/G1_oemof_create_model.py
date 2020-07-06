import logging
import sys
import oemof.solph as solph
import oemof.outputlib as outputlib

# todo this is called both from G0 and here
try:
   import src.G2a_oemof_busses_and_componets as generate
   import src.G2b_constraints_custom as constraints_custom

except ModuleNotFoundError:
    print("Module error at G1")
    from src.G2a_oemof_busses_and_componets import generate
    from src.G2b_constraints_custom import (
        stability_criterion,
        renewable_criterion,
        battery_management,
        ac_dc_bus,
    )

def load_energysystem_lp():
    # based on lp file
    return

def build(experiment, case_dict):
    logging.debug("Complete case dictionary:")
    logging.debug(case_dict)

    logging.debug(
        "Create oemof model by adding case-specific busses and components."
    )

    # create energy system
    micro_grid_system = solph.EnergySystem(timeindex=experiment[DATE_TIME_INDEX])

    ###################################
    ## AC side of the energy system   #
    ###################################

    logging.debug("Added to oemof model: Electricity bus of energy system, AC")
    bus_electricity_ac = solph.Bus(label=BUS_ELECTRICITY_AC)
    micro_grid_system.add(bus_electricity_ac)

    # ------------demand sink ac------------#
    sink_demand_ac = generate.demand_ac(
        micro_grid_system, bus_electricity_ac, experiment[DEMAND_PROFILE_AC]
    )

    # ------------fuel source------------#
    if case_dict[GENSET_FIXED_CAPACITY] != None:
        logging.debug("Added to oemof model: Fuel bus")
        bus_fuel = solph.Bus(label="bus_fuel")
        micro_grid_system.add(bus_fuel)
        generate.fuel(micro_grid_system, bus_fuel, experiment)

    # ------------genset------------#
    if case_dict[GENSET_FIXED_CAPACITY] == None:
        genset = None
    elif case_dict[GENSET_FIXED_CAPACITY] == False:
        if case_dict[GENSET_WITH_MINIMAL_LOADING] == True:
            # not possible with oemof
            logging.error(
                "It is not possible to optimize a generator with minimal loading in oemof. \n "
                + "    "
                + "    "
                + "    "
                + 'Please set GENSET_WITH_MINIMAL_LOADING=False for this case on tab CASE_DEFINITIONS in the excel template.'
            )
            sys.exit()
            # genset = generate.genset_oem_minload(micro_grid_system, bus_fuel, bus_electricity_ac, experiment, case_dict['number_of_equal_generators'])
        else:
            genset = generate.genset_oem(
                micro_grid_system,
                bus_fuel,
                bus_electricity_ac,
                experiment,
                case_dict[NUMBER_OF_EQUAL_GENERATORS],
            )

    elif isinstance(case_dict[GENSET_FIXED_CAPACITY], float):
        if case_dict[GENSET_WITH_MINIMAL_LOADING] == True:
            genset = generate.genset_fix_minload(
                micro_grid_system,
                bus_fuel,
                bus_electricity_ac,
                experiment,
                capacity_fuel_gen=case_dict[GENSET_FIXED_CAPACITY],
                number_of_equal_generators=case_dict[NUMBER_OF_EQUAL_GENERATORS],
            )
        else:
            genset = generate.genset_fix(
                micro_grid_system,
                bus_fuel,
                bus_electricity_ac,
                experiment,
                capacity_fuel_gen=case_dict[GENSET_FIXED_CAPACITY],
                number_of_equal_generators=case_dict[NUMBER_OF_EQUAL_GENERATORS],
            )
    else:
        logging.warning(
            "Case definition of "
            + case_dict[CASE_NAME]
            + " faulty at genset_fixed_capacity. Value can only be False, float or None"
        )

    # ------------wind------------#
    if case_dict[WIND_FIXED_CAPACITY] == None:
        wind_plant = None
    elif case_dict[WIND_FIXED_CAPACITY] == False:
        wind_plant = generate.wind_oem(
            micro_grid_system, bus_electricity_ac, experiment
        )

    elif isinstance(case_dict[WIND_FIXED_CAPACITY], float):
        wind_plant = generate.wind_fix(
            micro_grid_system,
            bus_electricity_ac,
            experiment,
            capacity_wind=case_dict[WIND_FIXED_CAPACITY],
        )

    else:
        logging.warning(
            "Case definition of "
            + case_dict[CASE_NAME]
            + " faulty at wind_fixed_capacity. Value can only be False, float or None"
        )

    # ------------ main grid bus and subsequent sources if necessary------------#
    if case_dict[PCC_CONSUMPTION_FIXED_CAPACITY] != None:
        # source + sink for electricity from grid
        bus_electricity_ng_consumption = generate.maingrid_consumption(
            micro_grid_system, experiment
        )

    if case_dict[PCC_FEEDIN_FIXED_CAPACITY] != None:
        # sink + source for feed-in
        bus_electricity_ng_feedin = generate.maingrid_feedin(
            micro_grid_system, experiment
        )

    # ------------point of coupling (consumption)------------#
    if case_dict[PCC_CONSUMPTION_FIXED_CAPACITY] == None:
        pointofcoupling_consumption = None
    elif case_dict[PCC_CONSUMPTION_FIXED_CAPACITY] == False:
        pointofcoupling_consumption = generate.pointofcoupling_consumption_oem(
            micro_grid_system,
            bus_electricity_ac,
            bus_electricity_ng_consumption,
            experiment,
            min_cap_pointofcoupling=case_dict[PEAK_DEMAND],
        )
    elif isinstance(case_dict[PCC_CONSUMPTION_FIXED_CAPACITY], float):
        pointofcoupling_consumption = generate.pointofcoupling_consumption_fix(
            micro_grid_system,
            bus_electricity_ac,
            bus_electricity_ng_consumption,
            experiment,
            cap_pointofcoupling=case_dict[PCC_CONSUMPTION_FIXED_CAPACITY],
        )
    else:
        logging.warning(
            "Case definition of "
            + case_dict[CASE_NAME]
            + " faulty at pcc_consumption_fixed_capacity. Value can only be False, float or None"
        )

    # ------------point of coupling (feedin)------------#
    if case_dict[PCC_FEEDIN_FIXED_CAPACITY] == None:
        pass
        # pointofcoupling_feedin = None
    elif case_dict[PCC_FEEDIN_FIXED_CAPACITY] == False:
        generate.pointofcoupling_feedin_oem(
            micro_grid_system,
            bus_electricity_ac,
            bus_electricity_ng_feedin,
            experiment,
            min_cap_pointofcoupling=case_dict[PEAK_DEMAND],
        )

    elif isinstance(case_dict[PCC_FEEDIN_FIXED_CAPACITY], float):
        generate.pointofcoupling_feedin_fix(
            micro_grid_system,
            bus_electricity_ac,
            bus_electricity_ng_feedin,
            experiment,
            capacity_pointofcoupling=case_dict[PCC_FEEDIN_FIXED_CAPACITY],
        )
    else:
        logging.warning(
            "Case definition of "
            + case_dict[CASE_NAME]
            + " faulty at pcc_feedin_fixed_capacity. Value can only be False, float or None"
        )

    ###################################
    ## DC side of the energy system   #
    ###################################

    # ------------DC electricity bus------------#
    logging.debug("Added to oemof model: Electricity bus of energy system, DC")
    bus_electricity_dc = solph.Bus(label=BUS_ELECTRICITY_DC)
    micro_grid_system.add(bus_electricity_dc)

    # ------------demand sink dc------------#
    sink_demand_dc = generate.demand_dc(
        micro_grid_system, bus_electricity_dc, experiment[DEMAND_PROFILE_DC]
    )

    # ------------PV------------#
    if case_dict[PV_FIXED_CAPACITY] == None:
        solar_plant = None
    elif case_dict[PV_FIXED_CAPACITY] == False:
        solar_plant = generate.pv_oem(
            micro_grid_system, bus_electricity_dc, experiment
        )

    elif isinstance(case_dict[PV_FIXED_CAPACITY], float):
        solar_plant = generate.pv_fix(
            micro_grid_system,
            bus_electricity_dc,
            experiment,
            capacity_pv=case_dict[PV_FIXED_CAPACITY],
        )

    else:
        logging.warning(
            "Case definition of "
            + case_dict[CASE_NAME]
            + " faulty at pv_fixed_capacity. Value can only be False, float or None"
        )

    # ------------storage------------#
    if case_dict[STORAGE_FIXED_CAPACITY] == None:
        storage = None
    elif case_dict[STORAGE_FIXED_CAPACITY] == False:
        storage = generate.storage_oem(
            micro_grid_system, bus_electricity_dc, experiment
        )

    elif isinstance(case_dict[STORAGE_FIXED_CAPACITY], float):
        storage = generate.storage_fix(
            micro_grid_system,
            bus_electricity_dc,
            experiment,
            capacity_storage=case_dict[STORAGE_FIXED_CAPACITY],
            power_storage=case_dict[STORAGE_FIXED_POWER],
        )  # changed order

    else:
        logging.warning(
            "Case definition of "
            + case_dict[CASE_NAME]
            + " faulty at genset_fixed_capacity. Value can only be False, float or None"
        )

    # ------------Rectifier AC DC------------#
    if case_dict[RECTIFIER_AC_DC_FIXED_CAPACITY] == None:
        rectifier = None

    elif case_dict[RECTIFIER_AC_DC_FIXED_CAPACITY] == False:
        rectifier = generate.rectifier_oem(
            micro_grid_system, bus_electricity_ac, bus_electricity_dc, experiment
        )

    elif isinstance(case_dict[RECTIFIER_AC_DC_FIXED_CAPACITY], float):
        rectifier = generate.rectifier_fix(
            micro_grid_system,
            bus_electricity_ac,
            bus_electricity_dc,
            experiment,
            case_dict[RECTIFIER_AC_DC_FIXED_CAPACITY],
        )

    else:
        logging.warning(
            "Case definition of "
            + case_dict[CASE_NAME]
            + " faulty at rectifier_ac_dc_capacity_. Value can only be False, float or None"
        )

    # ------------Inverter DC AC------------#
    if case_dict[INVERTER_DC_AC_FIXED_CAPACITY] == None:
        inverter = None

    elif case_dict[INVERTER_DC_AC_FIXED_CAPACITY] == False:
        inverter = generate.inverter_dc_ac_oem(
            micro_grid_system, bus_electricity_ac, bus_electricity_dc, experiment
        )

    elif isinstance(case_dict[INVERTER_DC_AC_FIXED_CAPACITY], float):
        inverter = generate.inverter_dc_ac_fix(
            micro_grid_system,
            bus_electricity_ac,
            bus_electricity_dc,
            experiment,
            case_dict[INVERTER_DC_AC_FIXED_CAPACITY],
        )

    else:
        logging.warning(
            "Case definition of "
            + case_dict[CASE_NAME]
            + " faulty at inverter_dc_ac_capacity. Value can only be False, float or None"
        )

    ###################################
    ## Global sinks / sources         #
    ###################################

    # ------------Excess sink------------#
    generate.excess(micro_grid_system, bus_electricity_ac, bus_electricity_dc)

    # ------------Optional: Shortage source------------#
    if case_dict[ALLOW_SHORTAGE] == True:
        source_shortage = generate.shortage(
            micro_grid_system,
            bus_electricity_ac,
            bus_electricity_dc,
            experiment,
            case_dict,
        )  # changed order
    else:
        source_shortage = None

    logging.debug("Create oemof model based on created components and busses.")
    model = solph.Model(micro_grid_system)

    # ------------Stability constraint------------#
    if case_dict[STABILITY_CONSTRAINT] == False:
        pass
    elif case_dict[STABILITY_CONSTRAINT] == SHARE_BACKUP:
        logging.info("Added constraint: Stability through backup.")
        constraints_custom.backup(
            model,
            case_dict,
            experiment=experiment,
            storage=storage,
            sink_demand=sink_demand_ac,
            genset=genset,
            pcc_consumption=pointofcoupling_consumption,
            source_shortage=source_shortage,
            el_bus_ac=bus_electricity_ac,
            el_bus_dc=bus_electricity_dc,
        )
    elif case_dict[STABILITY_CONSTRAINT] == SHARE_USAGE:
        logging.info("Added constraint: Stability though actual generation.")
        constraints_custom.usage(
            model,
            case_dict,
            experiment=experiment,
            storage=storage,
            sink_demand=sink_demand_ac,
            genset=genset,
            pcc_consumption=pointofcoupling_consumption,
            source_shortage=source_shortage,
            el_bus=bus_electricity_ac,
        )
    elif case_dict[STABILITY_CONSTRAINT] == SHARE_HYBRID:
        logging.info(
            "Added constraint: Stability though actual generation of diesel generators and backup through batteries."
        )
        constraints_custom.hybrid(
            model,
            case_dict,
            experiment=experiment,
            storage=storage,
            sink_demand=sink_demand_ac,
            genset=genset,
            pcc_consumption=pointofcoupling_consumption,
            source_shortage=source_shortage,
            el_bus_ac=bus_electricity_ac,
            el_bus_dc=bus_electricity_dc,
        )
    else:
        logging.warning(
            "Case definition of "
            + case_dict[CASE_NAME]
            + " faulty at stability_constraint. Value can only be False, float or None"
        )

    # ------------Renewable share constraint------------#
    if case_dict[RENEWABLE_SHARE_CONSTRAINT] == False:
        pass
    elif case_dict[RENEWABLE_SHARE_CONSTRAINT] == True:
        logging.info("Adding constraint: Renewable share.")
        constraints_custom.share(
            model,
            case_dict,
            experiment,
            genset=genset,
            pcc_consumption=pointofcoupling_consumption,
            solar_plant=solar_plant,
            wind_plant=wind_plant,
            el_bus_ac=bus_electricity_ac,
            el_bus_dc=bus_electricity_dc,
        )
    else:
        logging.warning(
            "Case definition of "
            + case_dict[CASE_NAME]
            + " faulty at renewable_share_constraint. Value can only be True or False"
        )

    # ------------Force charge from maingrid------------#
    if case_dict[FORCE_CHARGE_FROM_MAINGRID] == False:
        pass
    elif case_dict[FORCE_CHARGE_FROM_MAINGRID] == True:
        logging.info("Added constraint: Forcing charge from main grid.")
        constraints_custom.forced_charge(
            model, case_dict, bus_electricity_dc, storage, experiment
        )
    else:
        logging.warning(
            "Case definition of "
            + case_dict[CASE_NAME]
            + " faulty at force_charge_from_maingrid. Value can only be True or False"
        )

    # ------------Allow discharge only at maingrid blackout------------#
    if case_dict[DISCHARGE_ONLY_WHEN_BLACKOUT] == False:
        pass
    elif case_dict[DISCHARGE_ONLY_WHEN_BLACKOUT] == True:
        logging.info("Added constraint: Allowing discharge only at blackout times.")
        constraints_custom.discharge_only_at_blackout(
            model, case_dict, bus_electricity_dc, storage, experiment
        )
    else:
        logging.warning(
            "Case definition of "
            + case_dict[CASE_NAME]
            + " faulty at discharge_only_when_blackout. Value can only be True or False"
        )

    # ------------Allow inverter use only at maingrid blackout------------#
    if case_dict[ENABLE_INVERTER_ONLY_AT_BLACKOUT] == False:
        pass
    elif case_dict[ENABLE_INVERTER_ONLY_AT_BLACKOUT] == True:
        logging.info(
            "Added constraint: Allowing inverter use only at blackout times."
        )
        constraints_custom.inverter_only_at_blackout(
            model, case_dict, bus_electricity_dc, inverter, experiment
        )
    else:
        logging.warning(
            "Case definition of "
            + case_dict[CASE_NAME]
            + " faulty at enable_inverter_at_backout. Value can only be True or False"
        )

    """
    # ------------Allow shortage only for certain percentage of demand in a timestep------------#
    if case_dict['allow_shortage'] == True:
        if bus_electricity_ac != None:
            shortage_constraints.timestep(model, case_dict, experiment, sink_demand_ac, 
                                          source_shortage, bus_electricity_ac)
        if bus_electricity_dc != None:
            shortage_constraints.timestep(model, case_dict, experiment, sink_demand_dc, 
                                          source_shortage, bus_electricity_dc)
    """
    return micro_grid_system, model

def simulate(experiment, micro_grid_system, model, file_name):
    logging.info("Simulating...")
    model.solve(
        solver=experiment[SOLVER],
        solve_kwargs={
            "tee": experiment["solver_verbose"]
        },  # if tee_switch is true solver messages will be displayed
        cmdline_options={
            experiment["cmdline_option"]: str(experiment["cmdline_option_value"])
        },
    )  # ratioGap allowedGap mipgap
    logging.debug("Problem solved")

    if experiment[SAVE_LP_FILE] == True:
        logging.debug("Saving lp-file to folder.")
        model.write(
            experiment[OUTPUT_FOLDER] + "/lp_files/model_" + file_name + ".lp",
            io_options={"symbolic_solver_labels": True},
        )

    # add results to the energy system to make it possible to store them.
    micro_grid_system.results[MAIN] = outputlib.processing.results(model)
    micro_grid_system.results[META] = outputlib.processing.meta_results(model)
    return micro_grid_system

def store_results(micro_grid_system, file_name, output_folder):
    # store energy system with results
    micro_grid_system.dump(
        dpath=output_folder + "/oemof", filename=file_name + ".oemof"
    )
    logging.debug(
        "Stored results in " + output_folder + "/oemof" + "/" + file_name + ".oemof"
    )
    return micro_grid_system

def load_oemof_results(output_folder, file_name):
    logging.debug("Restore the energy system and the results.")
    micro_grid_system = solph.EnergySystem()
    micro_grid_system.restore(
        dpath=output_folder + "/oemof", filename=file_name + ".oemof"
    )
    return micro_grid_system
