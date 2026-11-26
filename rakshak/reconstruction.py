import csv
import io
import json


def write_csv(rows, delimiter=","):
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=delimiter, lineterminator="\n")

    for row in rows:
        writer.writerow(row)

    return output.getvalue()


def write_json(data):
    return json.dumps(
        data,
        ensure_ascii=False,
        indent=2
    ) + "\n"