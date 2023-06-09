import json
import logging
import os

from fhir.resources import construct_fhir_element
from fhir.resources.condition import Condition as fhirCondition
from fhir.resources.encounter import Encounter as fhirEncounter
from fhir.resources.observation import Observation as fhirObservation
from fhir.resources.patient import Patient as fhirPatient

from classes.address import Address
from classes.condition import Condition
from classes.encounter import Encounter
from classes.encounter_participant import EncounterParticipant
from classes.identifier import Identifier
from classes.language import Language
from classes.name import Name
from classes.observation import Observation
from classes.patient import Patient
from classes.telecom import Telecom
from utils import postgres_utils
from utils.postgres_utils import PostgresUtils

logging.basicConfig(level=logging.INFO, format="%(levelname)s-%(lineno)d- %(message)s")

address = Address()
condition = Condition()
encounter = Encounter()
encounter_participant = EncounterParticipant()
identifier = Identifier()
language = Language()
name = Name()
observation = Observation()
patient = Patient()
telecom = Telecom()


def main(data_path: str) -> None:
    """Iterates over fhir bundle files, separates out different fhir objects and inserts them into
       according postgres tables.

       Currently imports fhir entries of type patient, encounter,
       observation and condition. Some of these objects contain sub classes of currently
       impoted are address, name, language, identifier and telecom

    Args:
        data_path (str): path to folder of files to import

    Raises:
        e: if any error is caught close postgres connection gracefully
    """
    pg = postgres_utils.get_connection()
    # iterate over files
    directory = os.fsencode(data_path)
    try:
        for file in os.listdir(directory):
            filename = os.fsdecode(file)
            logging.info(f"Importing {filename}")
            f = open(f"{data_path}/{filename}")
            f = json.load(f)
            file_type = f.get("resourceType")
            if not file_type:
                print("Error no file type")
            bundle = construct_fhir_element(file_type, f)
            patient_id = None
            for entry in bundle.entry:
                resource = entry.resource
                if resource.resource_type == "Patient":
                    patient_id = resource.id
                    insert_patient_and_its_classes(pg, resource)
                elif resource.resource_type == "Encounter":
                    insert_encounter_and_its_classes(patient_id, pg, resource)
                elif resource.resource_type == "Observation":
                    insert_observation(patient_id, pg, resource)
                elif resource.resource_type == "Condition":
                    insert_condition(patient_id, pg, resource)
        logging.info("Import finished")

    except Exception as e:
        pg.connection.close()
        raise e


def insert_patient_and_its_classes(pg: PostgresUtils, resource: fhirPatient):
    """Creates a patient record and records for all its subclasses. Inserts them into postgres
    """
    patient_id = resource.id
    patient_dict = patient.from_fhir(resource)
    patient_sql = patient.to_insert_query()
    pg.execute(patient_sql, patient_dict)
    # Insert addresses
    addresses = address.from_fhir(patient_id, resource.address)
    address_sql = address.to_insert_query()
    pg.execute_many(address_sql, addresses)
    # Insert names
    names = name.from_fhir(patient_id, resource.name)
    names_sql = name.to_insert_query()
    pg.execute_many(names_sql, names)
    # Insert patient languages
    patient_languages = language.from_fhir(patient_id, resource.communication)
    languages_sql = language.to_insert_query()
    pg.execute_many(languages_sql, patient_languages)
    # Insert communication methods
    comm_methods = telecom.from_fhir(patient_id, resource.telecom)
    telecom_sql = telecom.to_insert_query()
    pg.execute_many(telecom_sql, comm_methods)
    # Insert identifiers
    identifiers = identifier.from_fhir(patient_id, resource.identifier)
    identifier_sql = identifier.to_insert_query()
    pg.execute_many(identifier_sql, identifiers)


def insert_encounter_and_its_classes(
        patient_id: str, pg: PostgresUtils, resource: fhirEncounter) -> None:
    """Creates an encounter record and insert it into postgres
    """
    _, encounter_dict = encounter.from_fhir(patient_id, resource)
    # Insert encounter
    encounterm_sql = encounter.to_insert_query()
    pg.execute(encounterm_sql, encounter_dict)
    participants, encounter_participants = encounter_participant.from_fhir(
        patient_id, resource.id, resource.participant
    )

    pg.insert_participants(participants, encounter_participants)


def insert_observation(patient_id: str, pg: PostgresUtils, resource: fhirObservation) -> None:
    """Creates an observation record and insert it into postgres
    """
    observation_dict = observation.from_fhir(patient_id, resource)
    observationm_sql = observation.to_insert_query()
    pg.execute(observationm_sql, observation_dict)


def insert_condition(patient_id: str, pg: PostgresUtils, resource: fhirCondition) -> None:
    """Creates a condition record and insert it into postgres
    """
    condition_dict = condition.from_fhir(patient_id, resource)
    condition_sql = condition.to_insert_query()
    pg.execute(condition_sql, condition_dict)


if __name__ == "__main__":
    data_path = f"{os.getcwd()}/data"
    main(data_path)
