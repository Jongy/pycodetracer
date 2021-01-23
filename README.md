# PyCodeTracer
(WIP) Instrument your code to trace each statement executed: view which statement runs and which data it operates on.

This tool is built with 2 goals in mind:
1. Educational - help beginners "code visualize" non-trivial concepts like recursion, generators; in general,
   let people view what *really* got executed.
2. Fast debugging - myself, an avid printf()-debugging guy, would like a way to quickly debug short scripts,
   without editing/appending debug statements.
   This tool may become *too* verbose to the point it's just too hard to read its output, but I hope it will
   remain readable enough to be useful for quick debugging purposes.

### TODOs:
* Support more AST types.. duh
* Create local variables where necessary, to avoid re-executing statements with side effects.

### Similar work
Some resources I've encountered/learned from while working on this.
* http://pythontutor.com/visualize.html - code & data visualizer, statement by statement. Useful for educational purposes but not for quick debugging.
* pytest asserts - `assert`s in pytest are rewritten to provide introspection on the data. I wanted to base on that work initially, but eventually decided not to. See https://pybites.blogspot.com/2011/07/behind-scenes-of-pytests-new-assertion.html for brief introduction.
* https://github.com/Jongy/gcc_assert_introspect - instrument C code to provide useful prints when `assert`s fail. Inspired by `pytest`'s asserts. Ideas in this project are based on that C one I wrote last year.
