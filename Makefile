.PHONY: build test clean serve

build:
	python3 src/build_catalog.py --output public --cache .cache --clean-generated

test:
	python3 -m unittest discover -s tests -v

serve:
	python3 -m http.server 8000 --directory public

clean:
	rm -rf public/data public/playlists .cache __pycache__ src/__pycache__ tests/__pycache__
