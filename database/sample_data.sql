-- Intelligent Helmet - example data for a first test run.
-- Fictional values: replace them with your own before a real test.

USE Projet_casque;

INSERT INTO utilisateur (Nom, Prenom, TypeSanguin, Allergies, ContactUrgence)
VALUES ('Dupont', 'Alex', 'O+', 'None', '+33600000000');

INSERT INTO contactsecours (IdSecours, Contact)
VALUES ('Secours_Lyon', '112');

INSERT INTO lieux (IdLieu, IdSecours, Region, TypeSport, Latitude, Longitude)
VALUES ('Campus_Doua', 'Secours_Lyon', 'Villeurbanne', 'Cyclisme', 45.783100, 4.877400);

-- IdentifiantCasque must match the device ID registered in TTN
INSERT INTO casque (IdentifiantCasque, IdCapteurLuminosite, IdCentraleInertielle, IdFlexiForce, IdentifiantUtilisateur)
VALUES ('arduino-mkr-1310-1', 1, 1, NULL, 1);
