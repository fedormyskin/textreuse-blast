import argparse, os, sys, json, gzip, codecs
sys.path.insert(0, "/home/avjves/oldsuomi")
from joblib import Parallel, delayed
import multiprocessing
from text_encoder import TextEncoder
import subprocess


class Blaster(object):

	def __init__(self, data, output, size, threads, min_length, subgraph, tsv, full):
		self.data_location = data
		self.encoder = TextEncoder("prot")
		self.output_folder = output
		self.db_size = 0
		self.threads = threads
		self.min_length = min_length
		self.flags = ""
		if subgraph:
			self.flags += " --subgraph"
		if tsv:
			self.flags += " --tsv"
		if full:
			self.flags += " --full"

	def run(self):
		self.encode_data()
		self.make_fasta()
		self.make_blast_db()
		self.run_blast()
		self.cluster_results()

	def encode_data(self):
		files = []
		if os.path.isdir(self.data_location):
			files = os.listdir(self.data_location)
		else:
			dl = self.data_location.split("/")
			filename = dl.pop(-1)
			self.data_location = "/".join(dl)
			files.append(filename)

		os.makedirs(self.output_folder + "/encoded")
		Parallel(n_jobs=self.threads)(delayed(self.encode)(filename, self.data_location) for filename in files)
		self.combine_metadata()

	def encode(self, filename, data_location):
		encoded_data = {}
		info = {}
		with open(data_location + "/" + filename) as json_file:
			jdata = json.load(json_file)
			for key, value in jdata.items():
				data = value
				text = data["text"]
				info[key] = {}
				info[key]["year"] = data["year"]
				info[key]["title"] = data["title"]
				info[key]["filename"] = filename
				encoded_data[key] = self.encoder.encode_text(text)
		with gzip.open(self.output_folder + "/encoded/" + filename + ".gz", "wb") as gzip_file:
			gzip_file.write(bytes(json.dumps(encoded_data), "utf-8"))
		os.makedirs(self.output_folder + "/metadata")
		with codecs.open(self.output_folder + "/metadata/" + str(multiprocessing.current_process()), "w") as json_file:
			json.dump(info, json_file)

	def combine_metadata(self):
		metadata = {}
		for filename in os.listdir(self.output_folder + "/metadata/"):
			with codecs.open(self.output_folder + "/metadata/" + filename) as json_file:
				jdata = json.load(json_file)
			metadata.update(jdata)
		with codecs.open(self.output_folder + "/metadata.json", "w") as json_file:
			json.dump(metadata, json_file)

	def make_fasta(self):
		gi = 0
		os.makedirs(self.output_folder + "/database")
		with codecs.open(self.output_folder + "/database/db.fsa", "w") as fasta_file:
			for encoded_file in os.listdir(self.output_folder + "/encoded"):
				with gzip.open(self.output_folder + "/encoded/" + encoded_file, "rb") as gzip_file:
					gdata = json.loads(str(gzip_file.read(), "utf-8"))
				for key, value in gdata.items():
					gi += 1
					fasta_file.write(">gi|" + str(gi) + " " + key + "\n")
					fasta_file.write(value + "\n")

		self.db_size = int(gi)


	def make_blast_db(self):
		os.system("makeblastdb -dbtype prot -parse_seqids -hash_index -title database -out " + self.output_folder + "/database/database -in " + self.output_folder + "/database/db.fsa")


	def run_blast(self):
		os.makedirs(self.output_folder + "/results")
		os.system("blastp -db " + self.output_folder + "/database/database -query " + self.output_folder + "/database/db.fsa -matrix BLOSUM62 -gapopen 3 -gapextend 11 -threshold 400 -word_size 7 -outfmt \"7 stitle qstart qend sstart send length ppos\" -num_threads " + str(self.threads) + " -evalue 1e-10 -out " + self.output_folder + "/results/result.tsv")

	def cluster_results(self):
		os.system("python3 cluster_result_file.py -f " + self.output_folder + "/results/result.tsv -l " + self.min_length + " -t prot -d " + self.data_location + " -o " + self.output_folder + self.flags)

if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Software to find repetitions within texts using BLAST.")
	parser.add_argument("-d", "--data", help='Location to either a data file or folder with JSON files. Json format: {"cluster_name": {"text": <text>, "year": <year>, "title": <title>, "cluster_2_name": {...}}', required=True)
	parser.add_argument("--num_process", help="Number of processes to launch when encoding data, will require that the data is split into at least as many JSON files", default=1, type=int)
	parser.add_argument("--out_folder", help="Output folder where all the data will be stored", required=True)
	parser.add_argument("--min_length", help="Minimum length", default=0)
	parser.add_argument("--subgraphs", action="store_true", help="Save subgraphs", default=False)
	parser.add_argument("--tsv", action="store_true", help="Store TSV-file", default=False)
	parser.add_argument("--full", action="store_true", help="Store full clusters", default=False)
	args = parser.parse_args()

	blaster = Blaster(args.data, args.out_folder, 0, args.num_process, args.min_length, args.subgraphs, args.tsv, args.full)
	blaster.run()

	print("Removing temp data...")
	os.system("rm -rf " + args.out_folder + "/database " + args.out_folder + "/encoded " + args.out_folder + "/metadata " + args.out_folder + "/results")