'''
For defining custom constraints of the micro grid solutions
'''
import pyomo.environ as po
import pprint as pp
import logging
import pandas as pd

class stability_criterion():

    def backup(model, case_dict, experiment, storage, sink_demand, genset, pcc_consumption, source_shortage, el_bus):
        '''
        Set a minimal limit for operating reserve of diesel generator + storage to aid PV generation in case of volatilities
        = Ensure stability of MG system

          .. math:: for t in lp_files.TIMESTEPS:
                stability_limit * demand (t) <= CAP_genset + stored_electricity (t) *invest_relation_output_capacity

        Parameters
        - - - - - - - -

        model: oemof.solph.model
            Model to which constraint is added. Has to contain:
            - Sink for demand flow
            - Transformer (genset)
            - Storage (with invest_relation_output_capacity)

        case_dict: dictionary, includes
            'stability_constraint': float
                    Share of demand that potentially has to be covered by genset/storage flows for stable operation
            'storage_fixed_capacity': False, float, None
            'genset_fixed_capacity': False, float, None

        storage: currently single object of class oemof.solph.components.GenericStorage
            To get stored capacity at t
            Has to include attibute invest_relation_output_capacity
            Can either be an investment object or have a nominal capacity

        sink_demand: currently single object of class oemof.solph.components.Sink
            To get demand at t

        genset: currently single object of class oemof.solph.network.Transformer
            To get available capacity genset
            Can either be an investment object or have a nominal capacity

        el_bus: object of class oemof.solph.network.Bus
            For accessing flow-parameters
        '''
        stability_limit = experiment['stability_limit']
        ## ------- Get CAP genset ------- #
        CAP_genset = 0
        if case_dict['genset_fixed_capacity'] != None:
            if case_dict['genset_fixed_capacity']==False:
                for number in range(1, case_dict['number_of_equal_generators']+ 1):
                    CAP_genset += model.InvestmentFlow.invest[genset[number], el_bus]
            elif isinstance(case_dict['genset_fixed_capacity'], float):
                for number in range(1, case_dict['number_of_equal_generators'] + 1):
                    CAP_genset += model.flows[genset[number], el_bus].nominal_value

        ## ------- Get CAP PCC ------- #
        CAP_pcc = 0
        if case_dict['pcc_consumption_fixed_capacity'] != None:
            if case_dict['pcc_consumption_fixed_capacity'] == False:
                CAP_pcc += model.InvestmentFlow.invest[pcc_consumption, el_bus]
            elif isinstance(case_dict['pcc_consumption_fixed_capacity'], float):
                CAP_pcc += case_dict['pcc_consumption_fixed_capacity'] # this didnt work - model.flows[pcc_consumption, el_bus].nominal_value

        def stability_rule(model, t):
            expr = CAP_genset
            ## ------- Get demand at t ------- #
            demand = model.flows[el_bus, sink_demand].actual_value[t] * model.flows[el_bus, sink_demand].nominal_value
            expr += - stability_limit * demand
            ## ------- Get shortage at t------- #
            if case_dict['allow_shortage'] == True:
                shortage = model.flow[source_shortage,el_bus,t]
                #todo is this correct?
                expr += + stability_limit * shortage
            ##---------Grid consumption t-------#
            # this should not be actual consumption but possible one  - like grid_availability[t]*pcc_consumption_cap
            if case_dict['pcc_consumption_fixed_capacity'] != None:
                expr += CAP_pcc * experiment['grid_availability'][t]

            ## ------- Get stored capacity storage at t------- #
            if case_dict['storage_fixed_capacity'] != None:
                stored_electricity = 0
                if case_dict['storage_fixed_capacity'] == False:  # Storage subject to OEM
                    stored_electricity += model.GenericInvestmentStorageBlock.capacity[storage, t]  - experiment['storage_capacity_min'] * model.GenericInvestmentStorageBlock.invest[storage]
                elif isinstance(case_dict['storage_fixed_capacity'], float): # Fixed storage subject to dispatch
                    stored_electricity += model.GenericStorageBlock.capacity[storage, t] - experiment['storage_capacity_min'] * storage.nominal_capacity
                else:
                    print ("Error: 'storage_fixed_capacity' can only be None, False or float.")
                expr += stored_electricity * experiment['storage_Crate_discharge'] * experiment['storage_efficiency_discharge']
            return (expr >= 0)

        model.stability_constraint = po.Constraint(model.TIMESTEPS, rule=stability_rule)

        return model

    def backup_test(case_dict, oemof_results, experiment, e_flows_df):
        '''
            Testing simulation results for adherance to above defined stability criterion
        '''
        if case_dict['stability_constraint']!=False:
            demand_profile = e_flows_df['Demand']

            if ('Stored capacity' in e_flows_df.columns):
                stored_electricity = e_flows_df['Stored capacity']
            else:
                stored_electricity = pd.Series([0 for t in demand_profile.index], index=demand_profile.index)

            if ('Grid availability' in e_flows_df.columns):
                pcc_capacity = oemof_results['capacity_pcoupling_kW'] * e_flows_df['Grid availability']
            else:
                pcc_capacity = pd.Series([0 for t in demand_profile.index], index=demand_profile.index)

            genset_capacity = oemof_results['capacity_genset_kW']

            if case_dict['allow_shortage'] == True:
                shortage = e_flows_df['Demand shortage']
            else:
                shortage = pd.Series([0 for t in demand_profile.index], index=demand_profile.index)

            boolean_test = [
                genset_capacity
                + (stored_electricity[t] - oemof_results['capacity_storage_kWh'] *  experiment['storage_capacity_min'])
                *  experiment['storage_Crate_discharge'] * experiment['storage_efficiency_discharge']
                + pcc_capacity[t]
                >= experiment['stability_limit'] * (demand_profile[t] - shortage[t])
                for t in range(0, len(demand_profile.index))
                ]

            if all(boolean_test) == True:
                logging.debug("Stability criterion is fullfilled.")
            else:
                ratio = pd.Series([
                    (genset_capacity
                     + (stored_electricity[t] - oemof_results['capacity_storage_kWh'] * experiment['storage_capacity_min'])
                     * experiment['storage_Crate_discharge'] * experiment['storage_efficiency_discharge']
                     + pcc_capacity[t]
                     - experiment['stability_limit'] * (demand_profile[t] - shortage[t]))
                    / (experiment['peak_demand'])
                    for t in range(0, len(demand_profile.index))], index=demand_profile.index)
                ratio_below_zero=ratio.clip_upper(0)
                stability_criterion.test_warning(ratio_below_zero, oemof_results, boolean_test)
        else:
            pass

    def hybrid(model, case_dict, experiment, storage, sink_demand, genset, pcc_consumption, source_shortage,
               el_bus):

        stability_limit = experiment['stability_limit']

        def stability_rule(model, t):
            expr = 0
            ## ------- Get demand at t ------- #
            demand = model.flows[el_bus, sink_demand].actual_value[t] * model.flows[el_bus, sink_demand].nominal_value

            expr += - stability_limit * demand

            ## ------- Get shortage at t------- #
            if case_dict['allow_shortage'] == True:
                shortage = model.flow[source_shortage, el_bus, t]
                expr += + stability_limit * shortage

            ## ------- Generation Diesel ------- #
            if case_dict['genset_fixed_capacity'] != None:
                for number in range(1, case_dict['number_of_equal_generators'] + 1):
                    expr += model.flow[genset[number], el_bus, t]

            ##---------Grid consumption t-------#
            if case_dict['pcc_consumption_fixed_capacity'] != None:
               expr += model.flow[pcc_consumption, el_bus, t]

            ## ------- Get stored capacity storage at t------- #
            if case_dict['storage_fixed_capacity'] != None:
                stored_electricity = 0
                if case_dict['storage_fixed_capacity'] == False:  # Storage subject to OEM
                    stored_electricity += model.GenericInvestmentStorageBlock.capacity[storage, t]  - experiment['storage_soc_min'] * model.GenericInvestmentStorageBlock.invest[storage]
                elif isinstance(case_dict['storage_fixed_capacity'], float): # Fixed storage subject to dispatch
                    stored_electricity += model.GenericStorageBlock.capacity[storage, t] - experiment['storage_soc_min'] * storage.nominal_capacity
                else:
                    print ("Error: 'storage_fixed_capacity' can only be None, False or float.")
                expr += stored_electricity * experiment['storage_Crate_discharge'] * experiment['storage_efficiency_discharge']
            return (expr >= 0)

        model.stability_constraint = po.Constraint(model.TIMESTEPS, rule=stability_rule)

        return model

    def hybrid_test(case_dict, oemof_results, experiment, e_flows_df):
        '''
            Testing simulation results for adherance to above defined stability criterion
        '''
        if case_dict['stability_constraint'] != False:
            demand_profile = e_flows_df['Demand']

            if case_dict['allow_shortage'] == True:
                shortage = e_flows_df['Demand shortage']
            else:
                shortage = pd.Series([0 for t in demand_profile.index], index=demand_profile.index)

            if ('Stored capacity' in e_flows_df.columns):
                stored_electricity = e_flows_df['Stored capacity']
            else:
                stored_electricity = pd.Series([0 for t in demand_profile.index], index=demand_profile.index)

            if ('Consumption from main grid (MG side)' in e_flows_df.columns):
                pcc_feedin = e_flows_df['Consumption from main grid (MG side)']
            else:
                pcc_feedin = pd.Series([0 for t in demand_profile.index], index=demand_profile.index)

            if ('Genset generation' in e_flows_df.columns):
                genset_generation = e_flows_df['Genset generation']
            else:
                genset_generation = pd.Series([0 for t in demand_profile.index], index=demand_profile.index)

            boolean_test = [
                genset_generation[t]
                + (stored_electricity[t] - oemof_results['capacity_storage_kWh'] * experiment['storage_soc_min'])
                     * experiment['storage_Crate_discharge'] * experiment['storage_efficiency_discharge']
                + pcc_feedin[t]
                >= experiment['stability_limit'] * (demand_profile[t] - shortage[t])
                for t in range(0, len(demand_profile.index))
            ]

            if all(boolean_test) == True:
                logging.debug("Stability criterion is fullfilled.")
            else:
                ratio = pd.Series([
                    (genset_generation[t]
                     + (stored_electricity[t] - oemof_results['capacity_storage_kWh'] * experiment['storage_soc_min'])
                     * experiment['storage_Crate_discharge'] * experiment['storage_efficiency_discharge']
                     + pcc_feedin[t] - experiment['stability_limit'] * (
                                 demand_profile[t] - shortage[t]))
                    / (experiment['peak_demand'])
                    for t in range(0, len(demand_profile.index))], index=demand_profile.index)
                ratio_below_zero = ratio.clip_upper(0)
                stability_criterion.test_warning(ratio_below_zero, oemof_results, boolean_test)

        else:
            pass

        return

    def usage(model, case_dict, experiment, storage, sink_demand, genset, pcc_consumption, source_shortage,
               el_bus):

        stability_limit = experiment['stability_limit']

        def stability_rule(model, t):
            expr = 0
            ## ------- Get demand at t ------- #
            demand = model.flows[el_bus, sink_demand].actual_value[t] * model.flows[el_bus, sink_demand].nominal_value

            expr += - stability_limit * demand

            ## ------- Get shortage at t------- #
            if case_dict['allow_shortage'] == True:
                shortage = model.flow[source_shortage, el_bus, t]
                expr += stability_limit * shortage

            ## ------- Generation Diesel ------- #
            if case_dict['genset_fixed_capacity'] != None:
                for number in range(1, case_dict['number_of_equal_generators'] + 1):
                    expr += model.flow[genset[number], el_bus, t]

            ##---------Grid consumption t-------#
            if case_dict['pcc_consumption_fixed_capacity'] != None:
               expr += model.flow[pcc_consumption, el_bus, t]

            ## ------- Get discharge storage at t------- #
            if case_dict['storage_fixed_capacity'] != None:
                expr += model.flow[storage, el_bus, t]
            return (expr >= 0)

        model.stability_constraint = po.Constraint(model.TIMESTEPS, rule=stability_rule)

        return model

    def usage_test(case_dict, oemof_results, experiment, e_flows_df):
        '''
            Testing simulation results for adherance to above defined stability criterion
        '''
        if case_dict['stability_constraint'] != False:
            demand_profile = e_flows_df['Demand']

            if case_dict['allow_shortage'] == True:
                shortage = e_flows_df['Demand shortage']
            else:
                shortage = pd.Series([0 for t in demand_profile.index], index=demand_profile.index)

            if ('Storage discharge' in e_flows_df.columns):
                storage_discharge = e_flows_df['Storage discharge']
            else:
                storage_discharge = pd.Series([0 for t in demand_profile.index], index=demand_profile.index)

            if ('Consumption from main grid (MG side)' in e_flows_df.columns):
                pcc_feedin = e_flows_df['Consumption from main grid (MG side)']
            else:
                pcc_feedin = pd.Series([0 for t in demand_profile.index], index=demand_profile.index)

            if ('Genset generation' in e_flows_df.columns):
                genset_generation = e_flows_df['Genset generation']
            else:
                genset_generation = pd.Series([0 for t in demand_profile.index], index=demand_profile.index)

            boolean_test = [
                genset_generation[t] + storage_discharge[t] + pcc_feedin[t] \
                >= experiment['stability_limit'] * (demand_profile[t] - shortage[t])
                for t in range(0, len(demand_profile.index))
            ]

            if all(boolean_test) == True:
                logging.debug("Stability criterion is fullfilled.")
            else:
                ratio = pd.Series([
                    (genset_generation[t] + storage_discharge[t] + pcc_feedin[t] - experiment['stability_limit'] * (
                                 demand_profile[t] - shortage[t]))
                    / (experiment['peak_demand'])
                    for t in range(0, len(demand_profile.index))], index=demand_profile.index)
                ratio_below_zero = ratio.clip_upper(0)
                stability_criterion.test_warning(ratio_below_zero, oemof_results, boolean_test)
        else:
            pass

        return

    def test_warning(ratio_below_zero, oemof_results, boolean_test):
        if abs(ratio_below_zero.values.min()) < 10 ** (-6):
            logging.warning(
                "Stability criterion is strictly not fullfilled, but deviation is less then e6.")
        else:
            logging.warning("ATTENTION: Stability criterion NOT fullfilled!")
            logging.warning('Number of timesteps not meeting criteria: ' + str(sum(boolean_test)))
            logging.warning('Deviation from stability criterion: ' + str(
                ratio_below_zero.values.mean()) + '(mean) / ' + str(
                ratio_below_zero.values.min()) + '(max).')
            oemof_results.update({'comments': oemof_results[
                                                  'comments'] + 'Stability criterion not fullfilled (max deviation ' + str(
                round(100 * ratio_below_zero.values.min(), 4)) + '%). '})
        return

class renewable_criterion():
    def share(model, case_dict, experiment, genset, pcc_consumption, solar_plant, wind_plant, el_bus): #wind_plant
        '''
        Resulting in an energy system adhering to a minimal renewable factor

          .. math::
                minimal renewable factor <= 1 - (fossil fuelled generation + main grid consumption * (1-main grid renewable factor)) / total_demand

        Parameters
        - - - - - - - -
        model: oemof.solph.model
            Model to which constraint is added. Has to contain:
            - Transformer (genset)
            - optional: pcc

        experiment: dict with entries...
            - 'min_res_share': Share of demand that can be met by fossil fuelled generation (genset, from main grid) to meet minimal renewable share
            - optional: 'main_grid_renewable_share': Share of main grid electricity that is generated renewably

        genset: currently single object of class oemof.solph.network.Transformer
            To get available capacity genset
            Can either be an investment object or have a nominal capacity

        pcc_consumption: currently single object of class oemof.solph.network.Transformer
            Connecting main grid bus to electricity bus of micro grid (consumption)

        el_bus: object of class oemof.solph.network.Bus
            For accessing flow-parameters
        '''

        def renewable_share_rule(model):
            fossil_generation = 0
            total_generation = 0

            if genset is not None:
                for number in range(1, case_dict['number_of_equal_generators'] + 1):
                    genset_generation_kWh = sum(model.flow[genset[number], el_bus, :])
                    total_generation += genset_generation_kWh
                    fossil_generation += genset_generation_kWh

            if pcc_consumption is not None:
                pcc_consumption_kWh = sum(model.flow[pcc_consumption, el_bus, :])
                total_generation += pcc_consumption
                fossil_generation += pcc_consumption_kWh * (1 - experiment['maingrid_renewable_share'])

            if solar_plant is not None:
                solar_plant_generation = sum(model.flow[solar_plant, el_bus, :])
                total_generation += solar_plant_generation

            if wind_plant is not None:
                wind_plant_generation = sum(model.flow[wind_plant, el_bus, :])
                total_generation += wind_plant_generation

            expr = (fossil_generation - (1-experiment['min_renewable_share'])*total_generation)
            return expr <= 0

        model.renewable_share_constraint = po.Constraint(rule=renewable_share_rule)

        return model

    def share_test(case_dict, oemof_results, experiment):
        '''
        Testing simulation results for adherance to above defined stability criterion
        '''
        if case_dict['renewable_share_constraint']==True:
            boolean_test = (oemof_results['res_share'] >= experiment['min_renewable_share'])
            if boolean_test == False:
                deviation = (experiment['min_renewable_share'] - oemof_results['res_share']) /experiment['min_renewable_share']
                if abs(deviation) < 10 ** (-6):
                    logging.warning(
                        "Minimal renewable share criterion strictly not fullfilled, but deviation is less then e6.")
                else:
                    logging.warning("ATTENTION: Minimal renewable share criterion NOT fullfilled!")
                    oemof_results.update({'comments': oemof_results['comments'] + 'Renewable share criterion not fullfilled. '})
            else:
                logging.debug("Minimal renewable share is fullfilled.")
        else:
            pass

        return

class battery_charge():
    def only_from_renewables_criterion(model, case_dict, experiment):

        def renewable_charge_rule(model):
            expr = 0

            expr = ()
            return expr <= 0

        model.renewable_share_constraint = po.Constraint(rule=renewable_charge_rule)

        return model

    def share_test(case_dict, oemof_results, experiment):
        '''
        Testing simulation results for adherance to above defined stability criterion
        '''
        if case_dict['renewable_share_constraint']==True:
            boolean_test = (oemof_results['res_share'] >= experiment['min_renewable_share'])
            if boolean_test == False:
                deviation = (experiment['min_renewable_share'] - oemof_results['res_share']) /experiment['min_renewable_share']
                if abs(deviation) < 10 ** (-6):
                    logging.warning(
                        "Minimal renewable share criterion strictly not fullfilled, but deviation is less then e6.")
                else:
                    logging.warning("ATTENTION: Minimal renewable share criterion NOT fullfilled!")
                    oemof_results.update({'comments': oemof_results['comments'] + 'Renewable share criterion not fullfilled. '})
            else:
                logging.debug("Minimal renewable share is fullfilled.")
        else:
            pass

        return