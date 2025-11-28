CREATE TABLE "Viaggio"(
    "id" VARCHAR(255) NOT NULL,
    "id_aereo" VARCHAR(255) NOT NULL,
    "Orario_arrivo" TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
    "Orario_partenza" TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
    "id_terminal" INTEGER NOT NULL,
    "id_piazzola" VARCHAR(255) NULL,
    "Provenienza" VARCHAR(255) NOT NULL,
    "Destinazione" VARCHAR(255) NOT NULL,
    "Stato" VARCHAR(255) NOT NULL,
    "ICAO" VARCHAR(255) NOT NULL,
    "Data" DATE NOT NULL
);
ALTER TABLE
    "Viaggio" ADD PRIMARY KEY("id");
CREATE TABLE "Aereo"(
    "Id" VARCHAR(255) NOT NULL,
    "Tipo" VARCHAR(255) NOT NULL,
    "Raggio" VARCHAR(255) NOT NULL,
    "Modello" VARCHAR(255) NOT NULL,
    "Capacita" INTEGER NOT NULL,
    "Stato" VARCHAR(255) NOT NULL,
    "Velocita" FLOAT(53) NOT NULL,
    "Livello_Carburante" FLOAT(53) NOT NULL,
    "Manutenzione" BOOLEAN NOT NULL,
    "CA" VARCHAR(255) NULL,
    "id_percorso" INTEGER NOT NULL
);
ALTER TABLE
    "Aereo" ADD PRIMARY KEY("Id");
CREATE TABLE "Piazzola"(
    "id" VARCHAR(255) NOT NULL,
    "Tipo" VARCHAR(255) NOT NULL,
    "id_terminal" INTEGER NOT NULL,
    "Stato" VARCHAR(255) NOT NULL,
    "id_aereo" VARCHAR(255) NULL
);
ALTER TABLE
    "Piazzola" ADD PRIMARY KEY("id");
CREATE TABLE "Terminal"(
    "id" INTEGER NOT NULL,
    "Tipo" VARCHAR(255) NOT NULL,
    "Capacita" INTEGER NOT NULL
);
ALTER TABLE
    "Terminal" ADD PRIMARY KEY("id");
CREATE TABLE "Veicolo"(
    "id" VARCHAR(255) NOT NULL,
    "Tipo" VARCHAR(255) NOT NULL,
    "Capacita" INTEGER NOT NULL,
    "Posizione" jsonb NOT NULL,
    "Destinazione" VARCHAR(255) NOT NULL,
    "Stato" VARCHAR(255) NOT NULL,
    "Velocita" FLOAT(53) NOT NULL,
    "id_percorso" INTEGER NOT NULL,
    "id_viaggio" VARCHAR(255) NOT NULL
);
ALTER TABLE
    "Veicolo" ADD PRIMARY KEY("id");
CREATE TABLE "Operazione"(
    "id" VARCHAR(255) NOT NULL,
    "TIpo" VARCHAR(255) NOT NULL,
    "id_viaggio" VARCHAR(255) NOT NULL,
    "id_aereo" VARCHAR(255) NOT NULL,
    "id_piazzola" VARCHAR(255) NOT NULL,
    "Stato" VARCHAR(255) NOT NULL
);
ALTER TABLE
    "Operazione" ADD PRIMARY KEY("id");
CREATE TABLE "Percorso"(
    "id" INTEGER NOT NULL,
    "Sorgente" VARCHAR(255) NOT NULL,
    "Destinazione" VARCHAR(255) NOT NULL,
    "Spline" INTEGER NOT NULL
);
ALTER TABLE
    "Percorso" ADD PRIMARY KEY("id");
CREATE TABLE "Passeggero"(
    "id" VARCHAR(255) NOT NULL,
    "Nome" VARCHAR(255) NOT NULL,
    "Cognome" VARCHAR(255) NOT NULL,
    "Sesso" VARCHAR(255) NOT NULL,
    "Eta" INTEGER NOT NULL,
    "id_viaggio" VARCHAR(255) NOT NULL,
    "id_bagaglio" VARCHAR(255) NOT NULL
);
ALTER TABLE
    "Passeggero" ADD PRIMARY KEY("id");
CREATE TABLE "Merce"(
    "id" VARCHAR(255) NOT NULL,
    "id_viaggio" VARCHAR(255) NOT NULL,
    "Tipo" VARCHAR(255) NOT NULL,
    "Quantita" INTEGER NOT NULL,
    "Peso" FLOAT(53) NOT NULL
);
ALTER TABLE
    "Merce" ADD PRIMARY KEY("id");
CREATE TABLE "Aeroporto"(
    "ICAO" VARCHAR(255) NOT NULL,
    "Nome" VARCHAR(255) NOT NULL,
    "Distanza" VARCHAR(255) NULL,
    "UTC" VARCHAR(255) NOT NULL,
    "Paese" VARCHAR(255) NOT NULL
);
ALTER TABLE
    "Aeroporto" ADD PRIMARY KEY("ICAO");
CREATE TABLE "Compagnia_Aerea"(
    "ICAO" VARCHAR(255) NOT NULL,
    "Nome" VARCHAR(255) NOT NULL,
    "Tipo" VARCHAR(255) NOT NULL
);
ALTER TABLE
    "Compagnia_Aerea" ADD PRIMARY KEY("ICAO");
CREATE TABLE "Parcheggio"(
    "id" INTEGER NOT NULL,
    "id_aereo" VARCHAR(255) NOT NULL,
    "Stato" VARCHAR(255) NOT NULL,
    "Spline" INTEGER NOT NULL
);
ALTER TABLE
    "Parcheggio" ADD PRIMARY KEY("id");
ALTER TABLE
    "Viaggio" ADD CONSTRAINT "viaggio_id_aereo_foreign" FOREIGN KEY("id_aereo") REFERENCES "Aereo"("Id");
ALTER TABLE
    "Passeggero" ADD CONSTRAINT "passeggero_id_viaggio_foreign" FOREIGN KEY("id_viaggio") REFERENCES "Viaggio"("id");
ALTER TABLE
    "Piazzola" ADD CONSTRAINT "piazzola_id_terminal_foreign" FOREIGN KEY("id_terminal") REFERENCES "Terminal"("id");
ALTER TABLE
    "Viaggio" ADD CONSTRAINT "viaggio_provenienza_foreign" FOREIGN KEY("Provenienza") REFERENCES "Aeroporto"("ICAO");
ALTER TABLE
    "Viaggio" ADD CONSTRAINT "viaggio_id_terminal_foreign" FOREIGN KEY("id_terminal") REFERENCES "Terminal"("id");
ALTER TABLE
    "Veicolo" ADD CONSTRAINT "veicolo_id_percorso_foreign" FOREIGN KEY("id_percorso") REFERENCES "Percorso"("id");
ALTER TABLE
    "Merce" ADD CONSTRAINT "merce_id_viaggio_foreign" FOREIGN KEY("id_viaggio") REFERENCES "Viaggio"("id");
ALTER TABLE
    "Piazzola" ADD CONSTRAINT "piazzola_id_aereo_foreign" FOREIGN KEY("id_aereo") REFERENCES "Aereo"("Id");
ALTER TABLE
    "Parcheggio" ADD CONSTRAINT "parcheggio_id_aereo_foreign" FOREIGN KEY("id_aereo") REFERENCES "Aereo"("Id");
ALTER TABLE
    "Operazione" ADD CONSTRAINT "operazione_id_piazzola_foreign" FOREIGN KEY("id_piazzola") REFERENCES "Piazzola"("id");
ALTER TABLE
    "Aereo" ADD CONSTRAINT "aereo_ca_foreign" FOREIGN KEY("CA") REFERENCES "Compagnia_Aerea"("ICAO");
ALTER TABLE
    "Operazione" ADD CONSTRAINT "operazione_id_viaggio_foreign" FOREIGN KEY("id_viaggio") REFERENCES "Viaggio"("id");
ALTER TABLE
    "Passeggero" ADD CONSTRAINT "passeggero_id_bagaglio_foreign" FOREIGN KEY("id_bagaglio") REFERENCES "Merce"("id");
ALTER TABLE
    "Viaggio" ADD CONSTRAINT "viaggio_destinazione_foreign" FOREIGN KEY("Destinazione") REFERENCES "Aeroporto"("ICAO");
ALTER TABLE
    "Veicolo" ADD CONSTRAINT "veicolo_id_viaggio_foreign" FOREIGN KEY("id_viaggio") REFERENCES "Viaggio"("id");
ALTER TABLE
    "Aereo" ADD CONSTRAINT "aereo_id_percorso_foreign" FOREIGN KEY("id_percorso") REFERENCES "Percorso"("id");
ALTER TABLE
    "Viaggio" ADD CONSTRAINT "viaggio_id_piazzola_foreign" FOREIGN KEY("id_piazzola") REFERENCES "Piazzola"("id");
ALTER TABLE
    "Operazione" ADD CONSTRAINT "operazione_id_aereo_foreign" FOREIGN KEY("id_aereo") REFERENCES "Aereo"("Id");