---
name: ub-mode
description: >
  Follow the reduced principles when writing or changing code. Every change
  follows First Make it Work, then Then Make it Right, then Follow Practice.
  Use when the user runs /ub-mode or asks for the reduced principles.
  In sketchup-mcp, use only for authorized FP-060 code/review work while FP-060-A01 is active.
---

# ub-mode

> Adapted for `GFCDOTA/sketchup-mcp` from [unclebob/ub-mode](https://github.com/unclebob/ub-mode) (MIT license; see `LICENSE`). The project's constitution, FP-060/FP-060-A01, Quality Guardian, and independent review policy take precedence. This skill provides engineering guidance, not authorization to execute, publish, approve, merge, or change scope.


Every time you are asked to make a change follow:
* First Make it Work.
* Then Make it Right.
* Follow Practice

# First Make it Work

## Laziness Protocol

* One decision lives in one place.
* Ship the smallest edit that solves the problem.

## Foundational Thinking

* Get the data shape right before you write the logic.
* Do first whatever helps every later phase.
* If a concurrent writer would matter, do not share state.

## TDD

* Write the failing test before you change the code.
* See it fail for the reason you expect.
* Make the smallest change that makes it pass.
* If an honest test is impractical, do not write a bad one.

## Redesign From First Principles

* Do not bolt a new requirement onto the old design.
* Ask what you would have built if it had been there from the start, think that through, and deliver it in pieces.

## Attack the Premise

* When two fixes that share one premise fail the same gate, write that premise in one sentence and count which actors hold the imbalance.
* Remove the assignment.
* Do not start another fix until you have done that.

## Subtract Before You Add

* Take complexity out before you add anything.

## Outcome-Oriented Execution

* Aim at the end state you can check.
* A break in the middle is allowed when you planned it and can undo it.

## Build the Lever

* If the work is not obvious at a glance, build the tool that does it.
* Do one unit by hand, then make the tool match that unit.

## Architecture

### Model the Domain

* Put the domain in a structure that makes the illegal states impossible.
* Maintain a glossary of domain terms.
* If the code is already clear and local, leave it.

### Boundary Discipline

* Check the data where it enters.
* Inside, trust it.
* Keep the business logic in a pure function.

### Type System Discipline

* Make the illegal value impossible to write.
* Parse outside data once, where it comes in.
* Do not silence the compiler.

### Make Operations Idempotent

* Running it twice, or running it after a crash halfway through, ends in the same state.

### Separate Before Serializing Shared State

* If they do not need the same mutable thing, give each its own.
* If they do, allow one writer, and enforce that in the structure.

# Then Make it Right

## Fix Root Causes

* Reproduce it.
* Fix the cause.
* A guard that only hides the crash is not a fix.

## Sequence work into verifiable units

* Finish one small unit and check it.
* Then start the next.

## Test Behavior, Not Implementation

* The test calls the code the way its user does and checks the result that user would see.
* If the test would still pass when every function returned nothing, throw it out.

## Crapper

* When installed and supported for the changed language, use the crapper tool
* Reduce each function under  CRAP 10 by splitting it, by testing it, or both.
* Consider whether case statements are worth reducing.

## Dryer

* When installed and supported for the changed language, use the dryer tool to eliminate duplication that rank 0.8 or above.

## Mutator

* When installed and supported for the changed language, use the mutator tool
* Cover the uncovered.
* Kill the survivors.
* Delete dead code.

## Refactoring

* Pin what the code does.
* Change the structure.
* Prove the behavior did not change.

# Practice

## Keep a Log

* Keep a log of every action you take and the reason you took it.
* Report that log upon completion.

## Guard the Context Window

* Keep the main thread small.
* Send the bulk elsewhere, and keep the summary.

## Worktree Cleanup

* Find what is safe to remove, confirm nothing still in use needs it, then reclaim the disk.
* Uncommitted work waits for a decision.

## Commit and Publish (sketchup-mcp policy)

* Prepare small, ordered changes and evidence; each commit should explain why, what changed, and how it was verified.
* Claude and Codex workers **must not** push, merge, approve PRs, or access GitHub publication credentials. Only the trusted Python executor/publisher may perform authorized staging, commits, and pushes.
* Never push directly to `develop` or `main`. Use protected PR workflow, required CI/Quality Guardian checks, and independent GitHub review. No automatic approval, merge, or `--execute` enablement.
* While FP-060-A01 is active, do not work on SketchUp geometry, furnishing, rendering, or apartment backlog. Apply this skill to the automation work only.
* CRAP/Dryer/Mutator are **not** automatically installed by this skill; do not claim their checks ran or make them mandatory CI gates without a separately reviewed integration.
