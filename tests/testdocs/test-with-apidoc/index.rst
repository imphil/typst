API Documentation Test
======================

C++ domain
----------

.. cpp:class:: template<typename T, int N> MyClass : public Base

   A class template.

   .. cpp:function:: int compute(const T &value, int flags = 0) const noexcept

      Compute something.

   .. cpp:member:: static constexpr int size = N

.. cpp:function:: void takes_callback(int (*cb)(int, char), unsigned n)

.. cpp:function:: template<typename ...Args> void variadic(Args &&...args)

Python domain
-------------

.. py:function:: spam(eggs, ham=None, *args, **kwargs)

   Spam.

.. py:function:: lead([a, ]b, c[, d])

.. py:function:: generic[T](x: T) -> T

.. py:class:: Foo(bar: int, baz: str = "x")

   .. py:method:: run(self, n: int = 3) -> bool

.. py:function:: over(a: int) -> int
                 over(a: str) -> str

   Two overloads sharing one body.

Other Sphinx nodes
------------------

.. seealso:: See :cpp:class:`MyClass`.

.. deprecated:: 1.2
   Use something else.

.. hlist::
   :columns: 2

   * one
   * two
   * three

.. centered:: Centered text

.. productionlist::
   try_stmt: try1_stmt | try2_stmt
   try1_stmt: "try" ":" `suite`

.. acks::

   * Someone

.. rubric:: A rubric

Inline: :cpp:expr:`a + b` and :manpage:`ls(1)`.
