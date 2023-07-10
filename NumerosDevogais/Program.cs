using System;

class Program
{
    static void Main()
    {
        Console.Write("Digite uma palavra: ");
        string nome = Console.ReadLine();

        int contador = 0;

        foreach (var letra in nome)
        {
            if (letra == 'a' || letra == 'A' ||
                letra == 'e' || letra == 'E' ||
                letra == 'i' || letra == 'I' ||
                letra == 'o' || letra == 'O' ||
                letra == 'u' || letra == 'U')
            {
                contador++;
            }
        }

        Console.WriteLine("Número de vogais é " + contador);
       
    }
}